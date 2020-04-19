#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Staging/live web site pubsubber for ASF git repos """
import asfpy.messaging
import asfpy.pubsub
import uuid
import git
import os
import time
import yaml
import threading
import ezt
import io
import re
import copy
import sys
import requests

PUBSUB_URL = 'http://pubsub.apache.org:2069/github'  # Subscribe to github events only
PUBSUB_QUEUE = {}
ROOT_DIRS = ['/x1/repos/asf', '/x1/repos/private']
SCHEME_FILE = 'notifications.yaml'
DEBUG = True if sys.argv[1:] else False
FALLBACK_ADDRESS = 'team@infra.apache.org'
DEFAULT_TEMPLATE = 'email_template.ezt'
EMAIL_SUBJECTS = {
    'open':         "opened a new %(type)s",
    'close':        "closed %(type)s",
    'merge':        "merged %(type)s",
    'comment':      "commented on %(type)s",
    'created':      "commented on %(type)s",
    'edited':       "edited a comment on %(type)s",
    'deleted':      "removed a comment on %(type)s",
    'diffcomment':  "commented on a change in %(type)s"
}

JIRA_DEFAULT_OPTIONS = 'link label'
JIRA_CREDENTIALS = '/x1/jirauser.txt'
jsplit = open(JIRA_CREDENTIALS).read().strip().split(':')
JIRA_AUTH = (jsplit[0], jsplit[1])
JIRA_HEADERS = {
    "Content-type": "application/json",
    "Accept": "*/*",
}

RE_PROJECT = re.compile(r"(?:incubator-)?([^-]+)")
RE_JIRA_TICKET = re.compile(r"\b([A-Z0-9]+-\d+)\b")

def jira_update_ticket(ticket, txt, worklog=False):
    """ Post JIRA comment or worklog entry """
    where = 'comment'
    data = {
        'body': txt
    }
    if worklog:
        where = 'worklog'
        data = {
            'timeSpent': "10m",
            'comment': txt
        }

    rv = requests.post(
        "https://issues.apache.org/jira/rest/api/latest/issue/%s/%s" % (ticket, where),
        headers=JIRA_HEADERS,
        auth=JIRA_AUTH,
        json=data
    )
    if rv.status_code == 200 or rv.status_code == 201:
        return "Updated JIRA Ticket %s" % ticket
    else:
        raise Exception(rv.text)


def jira_remote_link(ticket, url, prno):
    """ Post JIRA remote link to GitHub PR/Issue """
    urlid = url.split('#')[0] # Crop out anchor
    data = {
        'globalId': "github=%s" % urlid,
        'object':
            {
                'url': urlid,
                'title': "GitHub Pull Request #%s" % prno,
                'icon': {
                    'url16x16': "https://github.com/favicon.ico"
                }
            }
        }
    rv = requests.post(
        "https://issues.apache.org/jira/rest/api/latest/issue/%s/remotelink" % ticket,
        headers=JIRA_HEADERS,
        auth=JIRA_AUTH,
        json=data
        )
    if rv.status_code == 200 or rv.status_code == 201:
        return "Updated JIRA Ticket %s" % ticket
    else:
        raise Exception(rv.text)

def jira_add_label(ticket):
    """ Add a "PR available" label to JIRA """
    data = {
        "update": {
            "labels": [
                {"add": "pull-request-available"}
            ]
        }
    }
    rv = requests.put(
        "https://issues.apache.org/jira/rest/api/latest/issue/%s" % ticket,
        headers=JIRA_HEADERS,
        auth=JIRA_AUTH,
        json=data
    )
    if rv.status_code == 200 or rv.status_code == 201:
        return "Added PR label to Ticket %s\n" % ticket
    else:
        raise Exception(rv.text)


def get_recipient(repo, itype, action):
    """ Finds the right email recipient for a repo and an action. """
    scheme = {}
    m = RE_PROJECT.match(repo)
    if m:
        project = m.group(1)
    else:
        project = 'infra'
    for root_dir in ROOT_DIRS:
        repo_path = os.path.join(root_dir, "%s.git" % repo)
        if os.path.exists(repo_path):
            # Check for notifications.yaml first
            scheme_path = os.path.join(repo_path, SCHEME_FILE)
            if os.path.exists(scheme_path):
                try:
                    scheme = yaml.safe_load(open(scheme_path))
                except:
                    pass

            # Check standard git config
            cfg_path = os.path.join(repo_path, 'config')
            cfg = git.GitConfigParser(cfg_path)
            if not 'commits' in scheme:
                scheme['commits'] = cfg.get("hooks.asfgit", "recips", FALLBACK_ADDRESS)
            if cfg.has_option('apache', 'dev'):
                default_issue = cfg.get("apache", "dev")
                if not 'issues' in scheme:
                    scheme['issues'] = default_issue
                if not 'pullrequests' in scheme:
                    scheme['pullrequests'] = default_issue
            if cfg.has_option('apache', 'jira'):
                default_jira = cfg.get("apache", "jira")
                if not 'jira_options' in scheme:
                    scheme['jira_options'] = default_jira
            break

    if scheme:
        if itype not in ['commit', 'jira']:
            it = 'issues' if itype == 'issue' else 'pullrequests'
            if action in ['comment', 'diffcomment', 'edited', 'deleted', 'created']:
                if ("%s_comment" % it) in scheme:
                    return scheme["%s_comment" % it]
                elif it in scheme:
                    return scheme.get(it, FALLBACK_ADDRESS)
            elif action in ['open', 'close', 'merge']:
                if ("%s_status" % it) in scheme:
                    return scheme["%s_status" % it]
                elif it in scheme:
                    return scheme.get(it, FALLBACK_ADDRESS)
        elif itype == 'commit' and 'commits' in scheme:
            return scheme['commits']
        elif itype == 'jira':
            return scheme.get('jira_options', JIRA_DEFAULT_OPTIONS)
    if itype == 'jira':
        return JIRA_DEFAULT_OPTIONS
    return "dev@%s.apache.org" % project


class Event:
    def __init__(self, key, payload):
        self.key = key
        self.payload = payload
        self.user = payload.get('user')
        self.repo = payload.get('repo')
        self.tid = payload.get('id')
        self.title = payload.get('title')
        self.typeof = payload.get('type')
        self.action = payload.get('action', 'comment')
        self.link = payload.get('link', '')

        self.subject = None
        self.message = None
        self.recipient = None
        self.updated = time.time()

        if 'filename' in payload:
            self.add(payload)

    def add(self, payload):
        """ Turn into a stream of comments """
        if 'reviews' not in self.payload:
            self.payload['reviews'] = []
        self.payload['reviews'].append(Helper(payload))
        self.updated = time.time()

    def format_message(self, template = DEFAULT_TEMPLATE):
        self.payload['action_text'] = EMAIL_SUBJECTS.get(self.action, EMAIL_SUBJECTS['comment']) % self.payload
        self.subject = "[GitHub] [%(repo)s] %(user)s %(action_text)s #%(id)i: %(title)s" % self.payload
        template = ezt.Template(template, compress_whitespace=0)
        fp = io.StringIO()
        template.generate(fp, self.payload)
        self.message = fp.getvalue()

    def notify_jira(self):
        try:
            m = RE_JIRA_TICKET.search(self.title)
            if m:
                jira_ticket = m.group(1)
                jopts = get_recipient(self.repo, 'jira', '')
                if 'label' in jopts:
                    print("[INFO] Setting JIRA label for %s" % jira_ticket)
                    if not DEBUG:
                        jira_add_label(jira_ticket)
                if 'link' in jopts:
                    print("[INFO] Setting JIRA link for %s to %s" % (jira_ticket, self.link))
                    if not DEBUG:
                        jira_remote_link(jira_ticket, self.link, self.id)
                if 'worklog' in jopts or 'comment' in jopts:
                    print("[INFO] Adding comment to %s" % jira_ticket)
                    if not DEBUG:
                        jira_update_ticket(jira_ticket, self.message, True if 'worklog' in jopts else False)
        except Exception as e:
            print("[WARNING] Could not update JIRA: %s" % e)

    def send_email(self):
        recipient = get_recipient(self.repo, self.typeof, self.action)
        print("[INFO] Sending email to %s: %s" % (recipient, self.subject))
        if DEBUG:
            return
        if recipient == 'dev@null':
            return
        is_new_ticket = True if self.action == 'open' else False
        thread_id = "<%s.%s.%s.gitbox@gitbox.apache.org>" % (self.repo, self.tid, self.payload.get('node_id', '--'))
        message_id = thread_id if is_new_ticket else None
        reply_to_id = thread_id if not is_new_ticket else None

        sender = "GitBox <git@apache.org>"
        reply_headers = {
            'References': reply_to_id,
            'In-Reply-To': reply_to_id,
            } if reply_to_id else None
        try:
            asfpy.messaging.mail(
                sender=sender,
                recipient=recipient,
                subject=self.subject,
                message=self.message,
                messageid=message_id,
                headers=reply_headers
            )
        except Exception as e:
            raise Exception("Could not send email: " + str(e))

    def process(self):
        print("Processing %s (%u item(s))..." % (self.key, len(self.payload.get('reviews', []))))
        try:
            self.format_message()
            self.send_email()
            self.notify_jira()
        except Exception as e:
            print("Could not dispatch message: " + str(e))

class Helper(object):
  def __init__(self, xhash):
    self.__dict__.update(xhash)

class Actor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        """ Copy queue, clear it and run each item """
        while True:
            for key, event_object in PUBSUB_QUEUE.copy().items():
                now = time.time()
                if now - event_object.updated > 5:
                    del PUBSUB_QUEUE[key]
                    event_object.process()
            time.sleep(10)


def process(js):
    """ Plop the item into the queue, or (if stream of comments) append to existing queue item. """
    action = js.get('action', 'null')
    user = js.get('user', 'null')
    type_of = js.get('type')
    issue_id = js.get('id')
    repository = js.get('repo')
    key = "%s-%s-%s-%s-%s" % (action, repository, type_of, issue_id, user)

    # If not a file review, we don't want to fold...
    if 'filename' not in js:
        key += str(uuid.uuid4())
    if key not in PUBSUB_QUEUE:
        PUBSUB_QUEUE[key] = Event(key, js)
    else:
        PUBSUB_QUEUE[key].add(js)

if __name__ == '__main__':
    if DEBUG:
        print("[INFO] Debug mode enabled, no emails will be sent!")
    mail_actor = Actor()
    mail_actor.start()
    pubsub = asfpy.pubsub.Listener(PUBSUB_URL)
    pubsub.attach(process)
