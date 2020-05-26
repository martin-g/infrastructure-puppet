import requests
import json
import asfgit.log
import asfgit.git
import asfgit.cfg
import re
import github as pygithub
import os
import yaml
import asfpy.messaging

# LDAP to CNAME mappings for some projects
WSMAP = {
    'whimsy': 'whimsical',
    'empire': 'empire-db',
    'webservices': 'ws',
    'infrastructure': 'infra',
    'comdev': 'community',
}

# Notification scheme setup
NOTIFICATION_SETTINGS_FILE = 'notifications.yaml'
VALID_LISTS_FILE = '/x1/gitbox/mailinglists.json'
VALID_NOTIFICATION_SCHEMES = [
        'commits',
        'issues',
        'pullrequests',
        'issues_status',
        'issues_comment',
        'pullrequests_status',
        'pullrequests_comment',
        'jira_options'
]
# regex for valid ASF mailing list
RE_VALID_MAILINGLIST = re.compile(r"[-a-z0-9]+@[-a-z0-9]+(\.incubator)?\.apache\.org$")

def jenkins(cfg, yml):
    
    # GitHub PR Builder Whitelist for known (safe) contributors
    ref = yml.get('refname', 'master').replace('refs/heads/', '')
    if ref == 'master' or ref == 'trunk':
        ghprb_whitelist = yml.get('github_whitelist')
        if ghprb_whitelist and type(ghprb_whitelist) is list:
            if len(ghprb_whitelist) > 10:
                raise Exception("GitHub whitelist cannot be more than 10 people!")
            ghwl = "\n".join(ghprb_whitelist)
            print("Updating GHPRB whitelist for GitHub...")
            with open("/x1/gitbox/conf/ghprb-whitelist/%s.txt" % cfg.repo_name, "w") as f:
                f.write(ghwl)
                f.close()
            print("Whitelist updated!")

def custombuild(cfg, yml):
    """ Custom Command Builder """

    # Don't build from asf-site, like...ever
    ref = yml.get('refname', 'master').replace('refs/heads/', '')
    if ref == 'asf-site':
        print("Not auto-building from asf-site, ever...")
        return

    # If whoami specified, ignore this payload if branch does not match
    whoami = yml.get('whoami')
    if whoami and whoami != ref:
        return

    # Get target branch, if any, default to same branch
    target = yml.get('target', ref)

    # get the directory the build script will output it's generated content to.
    outputdir = yml.get('outputdir', None)

    # Get commands
    buildscript = yml.get('buildscript', None)
    if buildscript is None:
        print("No buildscript specified")
        return

    # infer project name
    m = re.match(r"(?:incubator-)?([^-.]+)", cfg.repo_name)
    pname = m.group(1)
    pname = WSMAP.get(pname, pname)

    # Get notification list
    pnotify = yml.get('notify', cfg.recips[0])

    # Contact buildbot 2
    bbusr, bbpwd = open("/x1/gitbox/auth/bb2.txt").read().strip().split(':', 1)
    import requests
    s = requests.Session()
    s.get("https://ci2.apache.org/auth/login", auth= (bbusr, bbpwd))

    if type(buildscript) is not str:
        raise ValueError("Buildscript invocation is not a string")
    else:
            payload = {
                "method": "force",
                "jsonrpc": "2.0",
                "id":0,
                "params":{
                    "reason": "Triggered custom builder via .asf.yaml by %s" % cfg.committer,
                    "builderid": "8",
                    "source": "https://gitbox.apache.org/repos/asf/%s.git" % cfg.repo_name,
                    "sourcebranch": ref,
                    "outputbranch": target,
                    "project": pname,
                    "buildscript": buildscript,
                    "outputdir": outputdir,
                    "notify": pnotify,
                }
            }
    print("Triggering custom build...")
    s.post('https://ci2.apache.org/api/v2/forceschedulers/custombuild_websites', json = payload)
    print("Done!")

def jekyll(cfg, yml):
    """ Jekyll auto-build """
    
    # Don't build from asf-site, like...ever
    ref = yml.get('refname', 'master').replace('refs/heads/', '')
    if ref == 'asf-site':
        print("Not auto-building from asf-site, ever...")
        return
    
    # If whoami specified, ignore this payload if branch does not match
    whoami = yml.get('whoami')
    if whoami and whoami != ref:
        return
    
    # Get target branch, if any, default to same branch
    target = yml.get('target', ref)
    
    # Get optional theme
    theme = yml.get('theme', 'theme')

    # Get optional outputdirectory name, Default 'output'
    outputdir = yml.get('outputdir', 'output')
    
    # infer project name
    m = re.match(r"(?:incubator-)?([^-.]+)", cfg.repo_name)
    pname = m.group(1)
    pname = WSMAP.get(pname, pname)
    
    # Get notification list
    pnotify = yml.get('notify', cfg.recips[0])
    
    # Contact buildbot 2
    bbusr, bbpwd = open("/x1/gitbox/auth/bb2.txt").read().strip().split(':', 1)
    import requests
    s = requests.Session()
    s.get("https://ci2.apache.org/auth/login", auth= (bbusr, bbpwd))
    
    payload = {
        "method": "force",
        "jsonrpc": "2.0",
        "id":0,
        "params":{
            "reason": "Triggered jekyll auto-build via .asf.yaml by %s" % cfg.committer,
            "builderid": "7",
            "source": "https://gitbox.apache.org/repos/asf/%s.git" % cfg.repo_name,
            "sourcebranch": ref,
            "outputbranch": target,
            "outputdir": outputdir,
            "project": pname,
            "theme": theme,
            "notify": pnotify,
        }
    }
    print("Triggering jekyll build...")
    s.post('https://ci2.apache.org/api/v2/forceschedulers/jekyll_websites', json = payload)
    print("Done!")

def pelican(cfg, yml):
    """ Pelican auto-build """
    
    # Don't build from asf-site, like...ever
    ref = yml.get('refname', 'master').replace('refs/heads/', '')
    if ref == 'asf-site':
        print("Not auto-building from asf-site, ever...")
        return
    
    # If whoami specified, ignore this payload if branch does not match
    whoami = yml.get('whoami')
    if whoami and whoami != ref:
        return
    
    # Get target branch, if any, default to same branch
    target = yml.get('target', ref)
    
    # Get optional theme
    theme = yml.get('theme', 'theme')
    
    # infer project name
    m = re.match(r"(?:incubator-)?([^-.]+)", cfg.repo_name)
    pname = m.group(1)
    pname = WSMAP.get(pname, pname)
    
    # Get notification list
    pnotify = yml.get('notify', cfg.recips[0])
    
    # Contact buildbot 2
    bbusr, bbpwd = open("/x1/gitbox/auth/bb2.txt").read().strip().split(':', 1)
    import requests
    s = requests.Session()
    s.get("https://ci2.apache.org/auth/login", auth= (bbusr, bbpwd))
    
    payload = {
        "method": "force",
        "jsonrpc": "2.0",
        "id":0,
        "params":{
            "reason": "Triggered pelican auto-build via .asf.yaml by %s" % cfg.committer,
            "builderid": "3",
            "source": "https://gitbox.apache.org/repos/asf/%s.git" % cfg.repo_name,
            "sourcebranch": ref,
            "outputbranch": target,
            "project": pname,
            "theme": theme,
            "notify": pnotify,
        }
    }
    print("Triggering pelican build...")
    s.post('https://ci2.apache.org/api/v2/forceschedulers/pelican_websites', json = payload)
    print("Done!")


def github(cfg, yml):
    """ GitHub settings updated. Can set up description, web site and topics """
    # Test if we need to process this
    ref = yml.get('refname', 'master').replace('refs/heads/', '')
    if ref != 'master':
        print("Saw GitHub meta-data in .asf.yaml, but not master branch, not updating...")
        return
    # Check if cached yaml exists, compare if changed
    ymlfile = '/tmp/ghsettings.%s.yml' % cfg.repo_name
    try:
        if os.path.exists(ymlfile):
            oldyml = yaml.safe_load(open(ymlfile).read())
            if cmp(oldyml, yml) == 0:
                return
    except yaml.YAMLError as e: # Failed to parse old yaml? bah.
        pass
    
    # Update items
    print("GitHub meta-data changed, updating...")
    GH_TOKEN = open('/x1/gitbox/matt/tools/asfyaml.txt').read().strip()
    GH = pygithub.Github(GH_TOKEN)
    repo = GH.get_repo('apache/%s' % cfg.repo_name)
    # If repo is on github, update accordingly
    if repo:
        desc = yml.get('description')
        homepage = yml.get('homepage')
        merges = yml.get('enabled_merge_buttons')
        features = yml.get('features')
        topics = yml.get('labels')
        ghp_branch = yml.get('ghp_branch')
        ghp_path = yml.get('ghp_path', '/docs')
        autolink = yml.get('autolink') # TBD: https://help.github.com/en/github/administering-a-repository/configuring-autolinks-to-reference-external-resources

        if desc:
            repo.edit(description=desc)
        if homepage:
            repo.edit(homepage=homepage)
        if merges:
            repo.edit(allow_squash_merge=merges.get("squash", False),
                allow_merge_commit=merges.get("merge", False),
                allow_rebase_merge=merges.get("rebase", False))
        if features:
            repo.edit(has_issues=features.get("issues", False),
                has_wiki=features.get("wiki", False),
                has_projects=features.get("projects", False))
        if topics and type(topics) is list:
            for topic in topics:
                if not re.match(r"^[-a-z0-9]{1,35}$", topic):
                    raise Exception(".asf.yaml: Invalid GitHub label '%s' - must be lowercase alphanumerical and <= 35 characters!" % topic)
            repo.replace_topics(topics)
        print("GitHub repository meta-data updated!")
        
        # GitHub Pages?
        if ghp_branch:
            GHP_URL = 'https://api.github.com/repos/apache/%s/pages?access_token=%s' % (cfg.repo_name, GH_TOKEN)
            # Test if GHP is enabled already
            rv = requests.get(GHP_URL, headers = {'Accept': 'application/vnd.github.switcheroo-preview+json'})
            
            # Not enabled yet, enable?!
            if rv.status_code == 404:
                try:
                    rv = requests.post(
                        GHP_URL,
                        headers = {'Accept': 'application/vnd.github.switcheroo-preview+json'},
                        json = {
                            'source': {
                                'branch': ghp_branch,
                                'path': ghp_path
                            }
                        }
                    )
                    print("GitHub Pages set to branch=%s, path=%s" % (ghp_branch, ghp_path))
                except:
                    print("Could not set GitHub Pages configuration!")
            # Enabled, update settings?
            elif rv.status_code == 200:
                ghps = 'master /docs'
                if ghp_branch == 'gh-pages':
                    ghps = 'gh-pages'
                elif not ghp_path:
                    ghps = 'master'
                try:
                    rv = requests.put(
                        GHP_URL,
                        headers = {'Accept': 'application/vnd.github.switcheroo-preview+json'},
                        json = {
                            'source': ghps,
                        }
                    )
                    print("GitHub Pages updated to %s" % ghps)
                except:
                    print("Could not set GitHub Pages configuration!")


        # Save cached version for late checks
        with open(ymlfile, "w") as f:
            f.write(yaml.dump(yml, default_flow_style=False))

def staging(cfg, yml):
    """ Staging for websites. Sample entry .asf.yaml entry:
      staging:
        profile: gnomes
        # would stage current branch at https://$project-gnomes.staged.apache.org/
        # omit profile to stage at $project.staged.a.o
    """
    # infer project name
    m = re.match(r"(?:incubator-)?([^-.]+)", cfg.repo_name)
    pname = m.group(1)
    pname = WSMAP.get(pname, pname)
    
    # Get branch
    ref = yml.get('refname', 'master').replace('refs/heads/', '')
    
    # If whoami specified, ignore this payload if branch does not match
    whoami = yml.get('whoami')
    if whoami and whoami != ref:
        return
    
    subdir = yml.get('subdir', '')
    if subdir:
        if not re.match(r"^[-_a-zA-Z0-9/]+$", subdir):
            raise Exception(".asf.yaml: Invalid subdir '%s' - Should be [-_A-Za-z0-9/]+ only!" % subdir)
    
    # Get profile from .asf.yaml, if present
    profile = yml.get('profile', '')
    
    # Try sending staging payload to pubsub
    try:
        payload = {
            'staging': {
                'project': pname,
                'subdir': subdir,
                'source': "https://gitbox.apache.org/repos/asf/%s.git" % cfg.repo_name,
                'branch': ref,
                'profile': profile,
                'pusher': cfg.committer,
            }
        }

        # Send to pubsub.a.o
        requests.post("http://pubsub.apache.org:2069/staging/%s" % pname,
                      data = json.dumps(payload))
        
        wsname = pname
        if profile:
            wsname += '-%s' % profile
        print("Staging contents at https://%s.staged.apache.org/ ..." % wsname)
    except Exception as e:
        print(e)
        asfgit.log.exception()

def publish(cfg, yml):
    """ Publishing for websites. Sample entry .asf.yaml entry:
      publish:
        whoami: asf-site
        # would publish current branch (if asf-site) at https://$project.apache.org/
    """
    # infer project name
    m = re.match(r"(?:incubator-)?([^-.]+)", cfg.repo_name)
    pname = m.group(1)
    pname = WSMAP.get(pname, pname)
    
    # Get branch
    ref = yml.get('refname', 'master').replace('refs/heads/', '')
    
    # Get optional target domain:
    target = yml.get('hostname', pname)
    if 'apache.org' in target:
        raise Exception(".asf.yaml: Invalid hostname '%s' - you cannot specify *.apache.org hostnames, they must be inferred!" % target)
    
    # If whoami specified, ignore this payload if branch does not match
    whoami = yml.get('whoami')
    if whoami and whoami != ref:
        return
    
    subdir = yml.get('subdir', '')
    if subdir:
        if not re.match(r"^[-_a-zA-Z0-9/]+$", subdir):
            raise Exception(".asf.yaml: Invalid subdir '%s' - Should be [-_A-Za-z0-9/]+ only!" % subdir)
    
    # Try sending publish payload to pubsub
    try:
        payload = {
            'publish': {
                'project': pname,
                'subdir': subdir,
                'source': "https://gitbox.apache.org/repos/asf/%s.git" % cfg.repo_name,
                'branch': ref,
                'pusher': cfg.committer,
                'target': target,
            }
        }

        # Send to pubsub.a.o
        requests.post("http://pubsub.apache.org:2069/publish/%s" % pname,
                      data = json.dumps(payload))
        
        print("Publishing contents at https://%s.apache.org/ ..." % pname)
    except Exception as e:
        print(e)
        asfgit.log.exception()


def notifications(cfg, yml):
    """ Notification scheme setup """

    # Get branch
    ref = yml.get('refname', 'master').replace('refs/heads/', '')

    # Ensure this is master, trunk or repo's default branch - otherwise bail
    if ref != 'master' and ref != 'trunk' and ref != asfgit.cfg.default_branch:
        print("[NOTICE] Notification scheme settings can only be applied to the master/trunk or default branch.")
        return

    # Grab list of valid mailing lists
    valid_lists = json.loads(open(VALID_LISTS_FILE).read())
    
    # infer project name
    m = re.match(r"(?:incubator-)?([^-.]+)", cfg.repo_name)
    pname = m.group(1)
    pname = WSMAP.get(pname, pname)

    # Verify that we know all settings in the yaml
    if not isinstance(yml, dict):
        raise Exception("Notification schemes must be simple 'key: value' pairs!")
    del yml['refname'] # Don't need this
    for k, v in yml.items():
        if not isinstance(v, str):
            raise Exception("Invalid value for setting '%s' - must be string value!" % k)
        if k not in VALID_NOTIFICATION_SCHEMES:
            raise Exception("Invalid notification scheme '%s' detected, please remove it!" % k)
        # Verify that all set schemes pass muster and point to $foo@$project.a.o
        if k != 'jira_options':
            if not RE_VALID_MAILINGLIST.match(v)\
                or not (
                    v.endswith('@%s.apache.org' % pname) or
                    v.endswith('@%s.incubator.apache.org' % pname)
                ) or v not in valid_lists:
                raise Exception("Invalid notification target '%s'. Must be a valid @%s.apache.org list!" % (v, pname))

    # All seems kosher, update settings if need be
    scheme_path = os.path.join(cfg.repo_dir, NOTIFICATION_SETTINGS_FILE)
    old_yml = {}
    if os.path.exists(scheme_path):
        old_yml = yaml.safe_load(open(scheme_path).read())

    # If old and new are identical, do nothing...
    if old_yml == yml:
        return

    print("Updating notification schemes for repository: ")
    changes = ""
    # Figure out what changed since last
    for key in VALID_NOTIFICATION_SCHEMES:
        if key not in old_yml and key in yml:
            changes += "- adding new scheme (%s): %s\n" % (key, yml[key])
        elif key in old_yml and key not in yml:
            changes += "- removing old scheme (%s) - was %s\n" % (key, old_yml[key])
        elif key in old_yml and key in yml and old_yml[key] != yml[key]:
            changes += "- updating scheme %s: %s -> %s" % (key, old_yml[key], yml[key])
    print(changes)
    
    with open(scheme_path, 'w') as fp:
        yaml.dump(yml, fp, default_flow_style=False)

    # Tell project what happened, on private@
    msg = "The following notification schemes have been changed on %s by %s:\n\n%s\n\nWith regards,\nASF Infra.\n" \
          % (cfg.repo_name, cfg.committer, changes)
    asfpy.messaging.mail(
        sender='GitBox <gitbox@apache.org>',
        recipients=['private@%s.apache.org' % pname],
        subject="Notification schemes for %s.git updated" % cfg.repo_name,
        message=msg)
