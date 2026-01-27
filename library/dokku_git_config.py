#!/usr/bin/python
# -*- coding: utf-8 -*-
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.frkl.infra.plugins.module_utils.dokku_utils import subprocess_check_output
import re
import shlex
import subprocess

DOCUMENTATION = """
---
module: dokku_git_config
short_description: Manage git configuration for dokku applications
description:
  - Configure git-related settings for a dokku application
  - Uses 'dokku git:report' to read and 'dokku git:set' to write
options:
  app:
    description:
      - The name of the app
    required: True
    type: str
  keep_git_dir:
    description:
      - Whether to keep the .git directory during builds
      - Set to "true" to keep, "false" to remove, or "" to reset to default
    required: False
    type: str
  rev_env_var:
    description:
      - Custom environment variable name for the git SHA
      - Set to a string like "DOKKU_GIT_REV" or "" to reset to default
    required: False
    type: str
  deploy_branch:
    description:
      - Branch to use for deployments
      - Set to branch name or "" to reset to default
    required: False
    type: str
author: Markus Binsteiner
"""

EXAMPLES = """
- name: Keep .git directory during builds
  dokku_git_config:
    app: myapp
    keep_git_dir: "true"

- name: Set custom git rev environment variable
  dokku_git_config:
    app: myapp
    rev_env_var: DOKKU_GIT_REV

- name: Configure deploy branch
  dokku_git_config:
    app: myapp
    deploy_branch: main

- name: Configure multiple git options
  dokku_git_config:
    app: myapp
    keep_git_dir: "true"
    rev_env_var: GIT_SHA
    deploy_branch: main

- name: Reset to defaults
  dokku_git_config:
    app: myapp
    keep_git_dir: ""
    rev_env_var: ""
    deploy_branch: ""
"""

# Mapping from module parameter names to dokku property names
PROPERTY_MAP = {
    "keep_git_dir": "keep-git-dir",
    "rev_env_var": "rev-env-var",
    "deploy_branch": "deploy-branch",
}

# Mapping from dokku report keys to module parameter names
REPORT_KEY_MAP = {
    "keep-git-dir": "keep_git_dir",
    "rev-env-var": "rev_env_var",
    "deploy-branch": "deploy_branch",
}


def get_git_report(app):
    """Get current git configuration for an app using dokku git:report."""
    command = "dokku --quiet git:report {0}".format(app)
    output, error = subprocess_check_output(command)
    if error is not None:
        return None, error

    # Normalize whitespace in output lines
    output = [re.sub(r"\s\s+", "", line) for line in output]
    report = {}

    for line in output:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        # Transform key: "Git keep git dir" -> "keep-git-dir"
        key = key.replace("Git ", "").replace(" ", "-").lower()
        if key in REPORT_KEY_MAP:
            report[REPORT_KEY_MAP[key]] = value.strip()

    return report, None


def set_git_property(app, prop, value):
    """Set a git property for an app using dokku git:set."""
    if value == "":
        # Empty string means reset to default (no value argument)
        command = "dokku --quiet git:set {0} {1}".format(app, prop)
    else:
        command = "dokku --quiet git:set {0} {1} {2}".format(
            app, prop, shlex.quote(value)
        )

    try:
        subprocess.check_call(command, shell=True)
        return True, None
    except subprocess.CalledProcessError as e:
        return False, str(e)


def main():
    fields = {
        "app": {"required": True, "type": "str"},
        "keep_git_dir": {"required": False, "type": "str", "default": None},
        "rev_env_var": {"required": False, "type": "str", "default": None},
        "deploy_branch": {"required": False, "type": "str", "default": None},
    }

    module = AnsibleModule(argument_spec=fields, supports_check_mode=False)

    app = module.params["app"]
    has_changed = False
    changed_keys = []
    meta = {"app": app, "changed": []}

    # Get current configuration
    report, error = get_git_report(app)
    if error:
        module.fail_json(msg="Failed to get git report: {0}".format(error), meta=meta)

    # Check each configurable property
    for param_name, dokku_prop in PROPERTY_MAP.items():
        desired_value = module.params.get(param_name)

        # Skip if not specified in module params
        if desired_value is None:
            continue

        current_value = report.get(param_name, "")

        # Compare current vs desired
        if desired_value == current_value:
            continue

        # Set the new value
        success, error = set_git_property(app, dokku_prop, desired_value)
        if error:
            module.fail_json(
                msg="Failed to set {0}: {1}".format(dokku_prop, error), meta=meta
            )

        has_changed = True
        changed_keys.append(param_name)

    meta["changed"] = changed_keys
    module.exit_json(changed=has_changed, meta=meta)


if __name__ == "__main__":
    main()
