import json
import os
import requests
from sys import exit as sys_exit

REQUIRED_KEYS = ['server_name', 'nice_name', 'direct_ip']
USERNAME_SOCIAL_KEYS = ['twitter', 'tiktok', 'facebook', 'instagram', 'teamspeak']
URL_SOCIAL_KEYS = ['web', 'web_shop', 'web_support', 'youtube', 'discord']
BRAND_KEYS = ['primary', 'background', 'text']


def main():
    comment = ''

    create_comment = comment_needed()
    if create_comment:
        print('No manifest file changed, comment will be skipped.')

    manifest_files = get_changed_manifest_files()

    if len(manifest_files) == 0:
        print('There are no changed manifest files in this pull request.')
        return

    for manifest_file in manifest_files:
        with open(manifest_file) as file:
            print(f'Open manifest file: {manifest_file}')

            try:
                data = json.load(file)
            except json.JSONDecodeError:
                comment += f'- JSON is invalid! Workflow is not able to check {manifest_file}\n'
                continue

        # Check for required keys
        if not all(key in data for key in REQUIRED_KEYS):
            comment += '- One of the **required values** is missing\n'
            continue

        check_server_online_state(data['direct_ip'])

        server_directory = manifest_file.replace('minecraft_servers/', '').replace('/manifest.json', '')
        if server_directory != data['server_name']:
            comment += '**Servername has to be directory name!**'

        # Check for https
        if 'social' in data:
            social = data['social']
            for key in URL_SOCIAL_KEYS:
                if key in social and not social[key].startswith('https://'):
                    comment += f'- Invalid url. URL has to start with **https://** (`social.{key}`)\n'

            for key in USERNAME_SOCIAL_KEYS:
                if key in social and (social[key].startswith('http') or 'www' in social[key]):
                    comment += f'- Please use a **username**, not a link (`social.{key}`)\n'

            # Check facebook, because it works :)
            if 'facebook' in social:
                facebook_username = social['facebook']
                request = requests.get(f'https://facebook.com/{facebook_username}')
                if request.status_code == 404:
                    comment += f'- Invalid facebook username not available: {facebook_username} ' \
                               f'(`social.facebook`)\n'

        # check for numeric server id (discord)
        if 'discord' in data:
            try:
                int(data['discord']['server_id'])
            except ValueError:
                comment += '- Please use a **numeric** value for your server id (`discord.server_id`)\n'

        if 'user_stats' in data and ('{userName}' not in data['user_stats'] and '{uuid}' not in data['user_stats']):
            comment += '- Please use {userName} or {uuid} in your stats url (`user_stats`)\n'

        # check hex codes
        if 'brand' in data:
            for key in BRAND_KEYS:
                if key in data['brand'] and '#' not in data['brand'][key]:
                    comment += f'- Please enter a valid hex-code (`brand.{key})`\n'

        if 'user_stats' in data:
            stats_url = data['user_stats']
            if not stats_url.startswith('https://'):
                comment += f'- Invalid url. URL has to start with **https://** (`user_stats`)\n'

            if '://laby.net/' in stats_url:
                comment += f'- Please use **your own page**, not LABY.net (`user_stats`)\n'

    if create_comment:
        post_comment(comment)

    for error in comment.split('\n'):
        # Print error comments, so that the user can relate the issues even if there is no comment
        print(error)

    if comment != '':
        # Make job fail
        sys_exit('Invalid data in manifest.json. See comments above or review in PR for more information.')


def get_changed_manifest_files():
    print('Getting changed files from json')

    with open('./files.json') as files:
        data = json.load(files)
        changed_files = [changed_file for changed_file in data if changed_file.endswith('manifest.json')
                         and changed_file.startswith('minecraft_servers/')]

    print(changed_files)

    return changed_files


def post_comment(comment: str, request_type: str = 'reviews'):
    if comment == '':
        print('No issues found.')
        return

    if request_type == 'reviews':
        comment += '\nPlease fix the issues by pushing **one** commit to the pull ' \
                   'request to prevent too many automatic reviews.'

    request = requests.post(
        f"https://api.github.com/repos/LabyMod/server-media/"
        f"{'pulls' if request_type == 'reviews' else 'issues'}/{os.getenv('PR_ID')}/{request_type}",
        json={'body': comment, 'event': 'REQUEST_CHANGES'},
        headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': f"Token {os.getenv('GH_TOKEN')}"}
    )

    print(f'Github request returned {request.status_code}')


def check_server_online_state(ip: str):
    print(f'Check server status for {ip}')

    url = f'https://api.mcsrvstat.us/2/{ip}'
    request = requests.get(url)

    try:
        response = json.loads(request.text)
    except json.JSONDecodeError:
        print(f'Cannot get value from server API. API returned {request.status_code} - Skipping...')
        return

    print(f"Checked server status successfully: {response['online']}")

    if not response['online']:
        post_comment(f'*Just as an information*:\nYour server {ip} **could be offline**.\n In general, we only accept '
                     f'pull requests from servers, **that are online**. Please change this, otherwise we '
                     f'cannot review your server correctly and have to deny the pull request.\n\n If your server is '
                     f'currently online, then our api returned a wrong status, we will have a look at it :)\n\n'
                     f'Reference: [API URL ({url})]({url})',
                     'comments')


def comment_needed():
    if os.getenv('PR_ACTION').endswith('opened'):
        print('PR opened - Write comment.')
        return True

    request = requests.get(
        os.getenv('COMMIT_URL')[:-6] + '/' + os.getenv('COMMIT_SHA'),
        headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': f"Token {os.getenv('GH_TOKEN')}"}
    )

    try:
        response = json.loads(request.text)
        if 'files' not in response:
            print('No changed files in commit.')
            return False

        return any(file['filename'].endswith('manifest.json') for file in response['files'])
    except json.JSONDecodeError:
        print(f'Cannot fetch commit.')

    return False


if __name__ == '__main__':
    main()
