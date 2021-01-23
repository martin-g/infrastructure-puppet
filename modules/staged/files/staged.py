#!/usr/bin/env python3
""" Staging/live web site pubsubber for ASF git repos """
import urllib.request
import asfpy.messaging
import syslog
import subprocess
import os
import time
import shutil
import re
import threading
import json
import socket

PUBSUB_URL = 'http://pubsub.apache.org:2069/'
PUBSUB_QUEUE = {}
GIT_CMD = '/usr/bin/git'
ROOT_DIR = '/www'
# Staging on staging-vm, publishing on tlp-* boxes
PUBLISH = True if 'tlp' in socket.gethostname() else False


def checkout_git_repo(path, source, branch):
    """ Checks out a new staging/publish site from a repo """
    os.chdir(ROOT_DIR)
    # If dir already exists as a dir, delete it first
    if os.path.isdir(path):
        syslog.syslog(syslog.LOG_INFO, "Doing recursive delete of path %s" % path)
        shutil.rmtree(path)
    # Try to pull in the repo, if it fails, just log it for now.
    syslog.syslog(syslog.LOG_INFO, "Checking out %s (%s) as %s..." % (source, branch, path))
    try:
        subprocess.check_output((GIT_CMD, "clone", "-b", branch, "--single-branch", source, path))
        syslog.syslog(syslog.LOG_INFO, "Checkout worked!")
    except subprocess.CalledProcessError as e:
        syslog.syslog(syslog.LOG_WARNING, "Could not check out %s: %s" % (source, e.output))


def do_git_pull(path, branch):
    """Does a simple git pull from a deploy dir, syslog if it works or not"""
    os.chdir(path)
    try:
        subprocess.check_output((GIT_CMD, 'pull', 'origin', branch), stderr=subprocess.STDOUT)
        syslog.syslog(syslog.LOG_INFO, "Successfully completed `git pull` into %s" % path)
    except subprocess.CalledProcessError as e:
        syslog.syslog(syslog.LOG_WARNING, "Could not `git pull` new contents into %s: %s" % (path, e.output))
        # If we hit a merge conflict due to rewritten history (detached tree), try a reset.
        if b"Merge conflict" in e.output or b"refusing to merge unrelated histories" in e.output or b"commit your changes or stash them before you merge" in e.output:
            syslog.syslog(syslog.LOG_INFO, "%s has merge conflicts or orphaned head, trying to reset the repository." % path)
            try:
                subprocess.check_output((GIT_CMD, 'reset', '--hard', 'origin/%s' % branch))
                syslog.syslog(syslog.LOG_INFO, "%s was successfully reset." % path)
            except subprocess.CalledProcessError as e:
                syslog.syslog(syslog.LOG_WARNING, "Could not `git reset --hard` in %s, giving up: %s" % (path, e.output))


def deploy_site(deploydir, source, branch, committer):
    """ Deploys a git repo to a staging/live site """

    # Pre-validation:
    if deploydir == 'www.apache.org':
        syslog.syslog(syslog.LOG_WARNING, "Not going to touch www.a.o, nope!!" % deploydir)
        return
    if (not re.match(r"^[-a-z0-9/.]+$", deploydir.replace('.apache.org', ''))) or re.search(r"\.\.", deploydir):
        syslog.syslog(syslog.LOG_WARNING, "Invalid deployment dir, %s!" % deploydir)
        return
    if not source.startswith('https://gitbox.apache.org/repos/asf/'):
        syslog.syslog(syslog.LOG_WARNING, "Invalid source URL, %s!" % source)
        return
    if not branch:
        syslog.syslog(syslog.LOG_WARNING, "Invalid branch, %s!" % branch)
        return

    # First check if staging dir is already being used.
    # If it is, check if we can just do a git pull...
    path = os.path.join(ROOT_DIR, deploydir)
    if os.path.isdir(path):
        syslog.syslog(syslog.LOG_INFO, "%s is an existing staging dir, checking it..." % path)
        os.chdir(path)
        try:
            csource = subprocess.check_output((GIT_CMD, 'config', '--get', 'remote.origin.url')).decode('utf-8').strip()
            cbranch = subprocess.check_output((GIT_CMD, 'symbolic-ref', '--short', 'HEAD')).decode('utf-8').strip()
        except subprocess.CalledProcessError as e:
            syslog.syslog(syslog.LOG_WARNING,
                          "Could not determine original source of %s, clobbering: %s" % (path, e.output))

            checkout_git_repo(path, source, branch)
            return
        # If different repo, clobber dir and re-checkout
        if csource != source:
            syslog.syslog(syslog.LOG_INFO,
                          "Source repo for %s is not %s (%s), clobbering repo." % (path, source, csource))
            checkout_git_repo(path, source, branch)
        # Or if different branch, switch
        elif cbranch != branch:
            syslog.syslog(syslog.LOG_INFO, "Source branch for %s is not %s, switching branches." % (path, branch))
            subprocess.check_output((GIT_CMD, 'stash'))  # Juuust in case
            subprocess.check_output((GIT_CMD, 'fetch', 'origin', branch))
            subprocess.check_output((GIT_CMD, 'checkout', '-b', branch, 'FETCH_HEAD'))
            do_git_pull(path, branch)
        # Or it could be all good, just needs a pull
        else:
            syslog.syslog(syslog.LOG_INFO, "Source and branch match on-disk, doing git pull")
            do_git_pull(path, branch)
    # Otherwise, do fresh checkout
    else:
        syslog.syslog(syslog.LOG_INFO, "%s is a new staging dir, doing fresh checkout" % path)
        checkout_git_repo(path, source, branch)


class deploy(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        """ Copy queue, clear it and run each item """
        global PUBSUB_QUEUE
        while True:
            XPQ = PUBSUB_QUEUE
            PUBSUB_QUEUE = {}
            for deploydir, opts in XPQ.items():
                try:
                    deploy_site(deploydir, opts[0], opts[1], opts[2])
                except Exception as e:
                    syslog.syslog(syslog.LOG_WARNING, "BORK: Could not deploy to %s: %s" % (deploydir, e))
            time.sleep(5)


def read_chunk(req):
    """ Processor func for reading "lines" (http chunks) """
    while True:
        try:
            line = req.readline().strip()
            if line:
                yield line
            else:
                break
        except Exception as info:
            syslog.syslog(syslog.LOG_WARNING, "Error reading from stream: %s" % info)
            break
    return


def listen():
    """ PubSub listener """
    last = time.time()
    now = last
    while True:
        syslog.syslog(syslog.LOG_INFO, "Subscribing to stream at %s" % PUBSUB_URL)
        req = None
        while not req:
            try:
                req = urllib.request.urlopen(PUBSUB_URL, None, 30)
                syslog.syslog(syslog.LOG_INFO, "Subscribed, reading stream")
            except:
                syslog.syslog(syslog.LOG_WARNING,
                              "Could not connect to pubsub service at %s, retrying in 30s..." % PUBSUB_URL)
                time.sleep(30)
                continue

        for line in read_chunk(req):
            line = line.decode('utf-8', errors='ignore').rstrip('\r\n,').replace('\x00', '')
            try:
                what = 'staging' if not PUBLISH else 'publish'
                obj = json.loads(line)
                if what in obj:
                    project = obj[what].get('project')
                    source = obj[what].get('source')
                    branch = obj[what].get('branch', 'asf-site').replace('refs/heads/', '')
                    profile = obj[what].get('profile', '')
                    committer = obj[what].get('pusher', 'root')
                    subdir = obj[what].get('subdir', '')

                    # Staging dir
                    deploydir = project
                    if profile:
                        deploydir += "-%s" % profile
                    # Or if publishing, use the tlp-server naming format
                    if PUBLISH:
                        deploydir = "%s.apache.org" % project
                        # Hardcoded hostnames (aoo etc):
                        if 'target' in obj[what]:
                            hostdir = obj[what].get('target')
                            if hostdir:
                                deploydir = hostdir  # Only if not empty value

                    if (deploydir and source and branch):
                        if subdir and re.match(r"^[-_a-zA-Z0-9/]+$", subdir):
                            syslog.syslog(syslog.LOG_INFO,
                                          "Extending deployment dir %s with subdir %s" % (deploydir, subdir))
                            deploydir = os.path.join(deploydir, subdir)
                        syslog.syslog(syslog.LOG_INFO,
                                      "Found deploy delivery for %s, deploying as %s" % (project, deploydir))
                        PUBSUB_QUEUE[deploydir] = [source, branch, committer]

            except ValueError as detail:
                syslog.syslog(syslog.LOG_WARNING, "Bad JSON or something: %s" % detail)
                continue
        syslog.syslog(syslog.LOG_WARNING, "Disconnected from %s, reconnecting" % PUBSUB_URL)


if __name__ == '__main__':
    deployer = deploy()
    deployer.start()
    listen()
