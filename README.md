# MauBot JIRA Plugin

A comprehensive MauBot plugin that automatically detects JIRA issue references in Matrix chat and provides issue information.

## Description

This plugin is a Matrix/MauBot port of the original IRC JIRA plugin from BrainzBot. It automatically monitors chat messages for JIRA issue keys (like `PROJECT-123`) and responds with the issue title and URL.

## Features

- **Automatic Issue Detection**: Detects JIRA issue keys in any message (format: `PROJECT-123`)
- **Smart Cooldown System**: Prevents spam by implementing a configurable cooldown period per issue
- **Project Validation**: Only responds to issues from known JIRA projects
- **Configurable Ignored Users**: Skip messages from specified users (like other bots)
- **URL Detection**: Optionally skip issues that are already part of URLs
- **Batch Processing**: Handle multiple issues in a single message
- **Off-topic Support**: Respects `[off]` prefix in messages
- **Manual Project Updates**: Command to refresh the list of JIRA projects

## Installation

1. Build the plugin:
   ```bash
   ./build.sh
   ```

2. Upload `jira.mbp` to your MauBot instance through the web interface

3. Create a plugin instance and assign it to a bot user

4. Configure the plugin

### Manual Commands

- `!jira update` - Updates the list of JIRA projects from the server
