#!/usr/bin/env python
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# This is issues.cgi: Handler for GitHub issues (and PRs)

import json
import os
import sys
import time
import cgi
import netaddr
import sqlite3
import git
import re
import ezt
import StringIO
import requests
import base64

# Define some defaults and debug vars
DEFAULT_JIRA_ENABLED = True         # Is JIRA bridge enabled by default?
DEFAULT_JIRA_ACTION = "comment"     # Default JIRA action (comment/worklog)

# CGI interface
xform = cgi.FieldStorage();

# Check that this is GitHub calling
from netaddr import IPNetwork, IPAddress
GitHubNetworks = [IPNetwork("185.199.108.0/22"), IPNetwork("192.30.252.0/22"), IPNetwork("140.82.112.0/20")]
callerIP = IPAddress(os.environ['REMOTE_ADDR'])
authed = False
for block in GitHubNetworks:
    if callerIP in block:
        authed = True
if not authed:
    print("Status: 401 Unauthorized\r\nContent-Type: text/plain\r\n\r\nI don't know you!\r\n")
    sys.exit(0)


### Helper functions ###
def getvalue(key):
    val = xform.getvalue(key)
    if val:
        return val
    else:
        return None

################################
# Message formatting functions #
################################

def get_type(payload):
    if 'pull_request' in payload:
        return 'pull request'
    if 'issue' in payload and '/pull/' in payload['issue']['html_url']:
        return 'pull request'
    return 'issue'

def issueOpened(payload):
    fmt = {}
    obj = payload['pull_request'] if 'pull_request' in payload else payload['issue']
    fmt['user'] = obj['user']['login']
    # PR or issue??
    fmt['type'] = get_type(payload)
    fmt['node_id'] = obj['node_id'] # Stable global issue/pr id
    fmt['id'] = obj['number']
    fmt['text'] = obj['body']
    fmt['title'] = obj['title']
    fmt['link'] = obj['html_url']
    fmt['action'] = 'open'
    return fmt

def issueClosed(payload, ml = "foo@bar"):
    fmt = {}
    obj = payload['pull_request'] if 'pull_request' in payload else payload['issue']
    fmt['user'] = payload['sender']['login'] if 'sender' in payload else obj['user']['login']
    # PR or issue??
    fmt['type'] = get_type(payload)
    fmt['id'] = obj['number']
    fmt['node_id'] = obj['node_id']
    fmt['text'] = "" # empty line when closing, so as to not confuse
    fmt['title'] = obj['title']
    fmt['link'] = obj['html_url']
    fmt['action'] = 'close'
    fmt['prdiff'] = None
    if obj.get('merged'): # Merged or just closed?
        fmt['action'] = 'merge'
    # If foreign diff, we have to pull it down here
    # TEMPORARILY DISABLED
    if False and obj.get('head') and obj['head'].get('repo') and obj['head']['repo'].get('full_name') and obj.get('diff_url'):
        if not obj['head']['repo']['full_name'].startswith("apache/"):
            txt = requests.get(obj['diff_url']).text
            addendum = None
            # No greater than 5MB or 20,000 lines, whichever comes first.
            if len(txt) > 5000000:
                txt = txt[:5000000]
                addendum = "This diff was greater than 5MB in size, and has been truncated"
            lines = txt.split("\n")
            if len(lines) > 20000:
                txt = "\n".join(lines[:20000])
                addendum = "This diff was longer than 20,000 lines, and has been truncated"
            if addendum:
                txt += "\n\n  (%s...)\n" % addendum
            fmt['prdiff'] = """
As this is a foreign pull request (from a fork), the diff has been
sent to your commit mailing list, %s
""" % ml
            fmt['prdiff_real'] = txt
    return fmt


def ticketComment(payload):
    fmt = {}
    obj = payload['pull_request'] if 'pull_request' in payload else payload['issue']
    comment = payload['comment']
    # PR or issue??
    fmt['type'] = get_type(payload)
    # This is different from open/close payloads!
    fmt['user'] = comment['user']['login']
    fmt['id'] = obj['number']
    fmt['node_id'] = obj['node_id']
    fmt['text'] = comment['body']
    fmt['title'] = obj['title']
    fmt['link'] = comment['html_url']
    fmt['action'] = payload.get('action', 'created')
    return fmt


def reviewComment(payload):
    fmt = {}
    obj = payload['pull_request'] if 'pull_request' in payload else payload['issue']
    comment = payload['comment']
    # PR or issue??
    fmt['type'] = get_type(payload)
    fmt['user'] = comment['user']['login']
    fmt['id'] = obj['number']
    fmt['node_id'] = obj['node_id']
    fmt['text'] = comment['body']
    fmt['title'] = obj['title']
    fmt['link'] = comment['html_url']
    fmt['action'] = "diffcomment"
    fmt['diff'] = comment['diff_hunk']
    fmt['filename'] = comment['path']
    return fmt

def formatMessage(fmt, template = 'template.ezt'):
    subjects = {
        'open':         "opened a new %(type)s",
        'close':        "closed %(type)s",
        'merge':        "merged %(type)s",
        'comment':      "commented on %(type)s",
        'created':      "commented on %(type)s",
        'edited':       "edited a comment on %(type)s",
        'deleted':      "removed a comment on %(type)s",
        'diffcomment':  "commented on a change in %(type)s"
    }
    fmt['action'] = (subjects[fmt['action']] if fmt['action'] in subjects else subjects['comment']) % fmt
    fmt['subject'] = "%(user)s %(action)s #%(id)i: %(title)s" % fmt
    template = ezt.Template(template)
    fp = StringIO.StringIO()
    output = template.generate(fp, fmt)
    body = fp.getvalue()
    return {
        'subject': "[GitHub] [%s] %s" % (fmt['repo'], fmt['subject']), # Append [GitHub] for mail filters
        'message': body
    }


# Main function
def main():
    # Get JSON payload from GitHub
    jsin = getvalue('payload')
    data = json.loads(jsin)

    # Now check if this repo is hosted on GitBox (if not, abort):
    if 'repository' in data:
        repo = data['repository']['name']
        repopath = "/x1/repos/asf/%s.git" % repo
    else:
        return None
    if not os.path.exists(repopath):
        return None

    # Get configuration options for the repo
    configpath = os.path.join(repopath, "config")
    if os.path.exists(configpath):
        gconf = git.GitConfigParser(configpath, read_only = True)
    else:
        return "No configuration found for repository %s" % repo

    # Now figure out what type of event we got
    fmt = None
    email = None
    isComment = False
    isNew = False
    if 'action' in data:
        # Issue opened or reopened
        if data['action'] in ['opened', 'reopened']:
            fmt = issueOpened(data)
        if data['action'] == 'opened':
            isNew = True
        # Issue closed
        elif data['action'] == 'closed':
            fmt = issueClosed(data, commitml)
        # Comment on issue or specific code (WIP)
        elif 'comment' in data:
            isComment = True
            # File-specific comment
            if 'path' in data['comment']:
                # Diff review
                if 'diff_hunk' in data['comment']:
                    fmt = reviewComment(data)
            # Standard commit comment
            elif 'commit_id' in data['comment']:
                # We don't quite handle this yet
                pass
            # Generic comment
            else:
                fmt = ticketComment(data)

    # Send pubsub event
    if fmt:
        fmt['repo'] = repo
        for el in ['filename','diff', 'prdiff']:
            if not el in fmt:
                fmt[el] = None
        # Indent comment
        fmt['text'] = "\n".join("   %s" % x for x in fmt['text'].split("\n"))
        
        m = re.match(r"(?:incubator-)([^-]+)", repo)
        project = "infra" # Default to infra
        if m:
            project = m.group(1)
        
        # Push even to pubsub
        act = fmt.get('type', 'issue')
        if act == 'pull request':
            act = 'pr'
        try:
            requests.post('http://pubsub.apache.org:2069/github/%s/%s/%s.git/%s' % (act, project, repo, fmt.get('action', 'unknown')), data = json.dumps({"payload": fmt}))
        except:
            pass
    
    # All done!
    return None

if __name__ == '__main__':
    rv = main()                                          # run main block
    print("Status: 204 Message received\r\n\r\n")   # Always return this
    # If error was returned, log it in issues.log
    if rv:
        try:
            open("/x1/gitbox/issues.log", "a").write(rv + "\r\n")
        except:
            pass
