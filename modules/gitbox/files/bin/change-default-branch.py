#!/usr/bin/env python3
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

import requests
import sys
import configparser
import os

"""Default branch change script
Instructions: 
- Run /x1/gitbox/bin/change-default-branch.py [newdefault]
- Paste each repo to change into the program, one per line.
- For branch overrides, you can paste in "repo.git newbranchhere"
- Confirm and execute with Ctrl+D (ends STDIN)

Examples with cfb.py main:

foo                       <-- change apache/foo.git to main branch
bar.git                   <-- change apache/bar.git to main branch
baz.git somethirdbranch   <-- change apache/baz.git to somethirdbranch

Alternate usage: cdb.py < somelist.txt
Default new target branch, unless specified as CLI arg 1, is main.
"""


REPO_ROOT = "/x1/repos/asf"  # Root dir for all repos
CONFIG_FILE = "/x1/gitbox/matt/tools/grouper.cfg"  # config file with GH token in it


def change_default_branch(repo: str, branch: str, token: str):
    repo = repo.replace(".git", "")
    headers = {"Authorization": "token %s" % token, "Content-Type": "application/json"}
    data = {"name": repo, "default_branch": branch}
    url = "https://api.github.com/repos/apache/%s" % repo

    print("Requesting branch change for %s on GitHub to %s..." % (repo, branch))
    requests.patch(url, json=data, headers=headers)

    repo += ".git"
    print("Changing HEAD file locally on GitBox for %s to %s..." % (repo, branch))
    with open(os.path.join(REPO_ROOT, repo, "HEAD", "w")) as f:
        f.write("ref: refs/heads/%s" % branch)

    print("Done with %s" % repo)


def main():
    defbranch = "main"
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            sys.stderr.write("Usage: change-default-branch.py [newbranch]\n")
            sys.stderr.write(
                "Enter repo names to change branch for on consecutive lines in stdin\n"
            )
            sys.stderr.write("and execute with ctrl+D")
            sys.exit(-1)
        else:
            defbranch = sys.argv[1]

    # Grab token from grouper
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)  # Shhhh
    token = cfg.get("github", "token")
    token = 'foo'

    for line in sys.stdin.readlines():
        line = line.strip()
        if line:
            if " " in line:
                repo, branch = line.split(" ", 1)
            else:
                repo = line
                branch = defbranch
            repo = repo.replace(".git", "")
            repo += ".git"
            print("Processing %s" % repo)
            change_default_branch(repo, branch, token)


if __name__ == "__main__":
    main()
