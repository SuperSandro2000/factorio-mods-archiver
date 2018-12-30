#!/usr/bin/env python3
from optparse import OptionParser
from subprocess import Popen, PIPE
from time import sleep
import json
import logging
import os
import requests

logging.basicConfig(filename='archiver.log', level=logging.WARN)


parser = OptionParser()
parser.add_option("-u", "--user", dest="user", default="",
                  help="sets the user name to download with", metavar="USER")
parser.add_option("-t", "--token", dest="token", default="",
                  help="sets the token to download with", metavar="TOKEN")
parser.add_option("-d", "--directory", dest="dir", default="data",
                  help="write data to FOLDER", metavar="FOLDER")
parser.add_option("-D", "--download", action="store_false", dest="download", default=True,
                  help="wether to download archives. Default: true")
# parser.add_option("-q", "--quiet", action="store_false", dest="verbose", default=False,
#                   help="don't print status messages to stdout")

(options, args) = parser.parse_args()

columns, _ = os.get_terminal_size()

if options.user is None or options.token is None:
    print("Set --user USER and --token TOKEN")
    exit()
data_file = "{}.json".format(options.dir)
mods_file = "{}/mods.json".format(options.dir)
mods_cache_file = "{}/mods-cache.json".format(options.dir)


if os.path.exists(data_file):
    with open(data_file, "r") as f:
        data = json.load(f)
else:
    data = {}

if os.path.isdir(options.dir):
    if os.path.exists(mods_file):
        with open(mods_file, "r") as f:
            mods_cached = json.load(f)
        if os.path.exists(mods_cache_file):
            os.remove(mods_cache_file)
        os.rename(mods_file, mods_cache_file)
else:
    os.makedirs(options.dir, exist_ok=True)

mods_req = requests.get("https://mods.factorio.com/api/mods?page_size=max")
if mods_req.status_code != 200:
    logging.warning(mods_req.prepare())
    exit()
mods = mods_req.json()

with open(mods_file, "w") as f:
    json.dump(mods, f, indent=2, sort_keys=True)


mod_count = len(mods["results"])
for i, mod in enumerate(mods["results"]):
    # if i == 10:
    #     break

    out = "Processing mod {} of {}: Comparing versions of {}".format(i, mod_count, mod["name"])
    print("{}{}".format(out, " " * (columns - len(out))), end="\r", flush=True)

    mod_folder = "{}/{}".format(options.dir, mod["name"])
    if not os.path.isdir(mod_folder):
        os.makedirs(mod_folder, exist_ok=True)

    # mod was processed before
    if mod["name"] in data:
        versions = []
        for k in data[mod["name"]]["releases"]:
            versions.append(data[mod["name"]]["releases"][k]["version"])
        if mod["latest_release"]["version"] in versions:
            continue

    # data entry empty, then process all archives
    else:
        data[mod["name"]] = {}
        data[mod["name"]]["releases"] = {}

    # update archives
    out = "Processing mod {} of {}: Getting data for {}".format(i, mod_count, mod["name"])
    print("{}{}".format(out, " " * (columns - len(out))), end="\r", flush=True)
    mod_data_req = requests.get("https://mods.factorio.com/api/mods/{}/full".format(mod["name"]))
    if mod_data_req.status_code != 200:
        logging.warning(mods_req.prepare())
        exit()
    mod_data = mod_data_req.json()
    with open("{}/mod.json".format(mod_folder), 'w') as f:
        json.dump(mod_data, f, indent=2, sort_keys=True)

    for j, release in enumerate(mod_data["releases"]):
        release_id = release["download_url"].split("/")[3]
        if release_id in data[mod["name"]]["releases"]:
            continue

        if not release_id in data[mod["name"]]["releases"]:
            data[mod["name"]]["releases"][release_id] = {}
        archive = data[mod["name"]]["releases"][release_id]
        archive["file_name"] = release["file_name"]
        archive["sha1"] = release["sha1"]
        archive["version"] = release["version"]

        out = "Processing mod {} of {}: Downloading {}".format(i, mod_count, archive["file_name"])
        print("{}{}".format(out, " " * (columns - len(out))), end="\r", flush=True)

        url = "https://mods.factorio.com{}?username={}&token={}".format(
            release["download_url"], options.user, options.token)
        os.system("curl -Ls \"{}\" -o \"{}/{}\"".format(url, mod_folder, archive["file_name"]))

        sha1_file = "{}.sha1".format(os.path.splitext(archive["file_name"])[0])
        with open("{}/{}".format(mod_folder, sha1_file), "w") as f:
            f.write("{} *{}\n".format(archive["sha1"], archive["file_name"]))
        p = Popen(["sha1sum", "-c", sha1_file], cwd=mod_folder, stdout=PIPE)
        output = p.communicate()[0]
        if p.returncode != 0:
            logging.warning("sha1 mismatch at %s/%s", mod["name"], archive["file_name"])

    with open(data_file, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    sleep(1)

os.remove(mods_cache_file)
