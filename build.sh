#!/bin/bash

# Build script for maubot-jira plugin

set -e

rm -f jira.mbp

zip -r jira.mbp maubot.yaml base-config.yaml jira/
