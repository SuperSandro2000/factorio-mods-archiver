#!/usr/bin/env python3
from optparse import OptionParser
from subprocess import Popen, PIPE
import json
import logging
import os
import requests
import signal


class DelayedKeyboardInterrupt(object):
    def __enter__(self):
        self.signal_received = False
        self.old_handler = signal.signal(signal.SIGINT, self.handler)

    def handler(self, sig, frame):
        self.signal_received = (sig, frame)
        logging.debug("SIGINT received. Delaying KeyboardInterrupt.")

    def __exit__(self, type, value, traceback):
        signal.signal(signal.SIGINT, self.old_handler)
        if self.signal_received:
            self.old_handler(*self.signal_received)


logFile = "archiver-py.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7.7s  %(message)s",
    handlers=[logging.FileHandler("{}".format(logFile)), logging.StreamHandler()],
)

parser = OptionParser()
parser.add_option(
    "-a",
    "--check-all",
    action="store_true",
    default=False,
    dest="check_all",
    help="Not only check if latest version is already downloaded. This considerable slows down the script execution but does not miss some old, not downloaded mods.",
)
parser.add_option(
    "-A",
    "--upload-all",
    action="store_true",
    dest="upload_all",
    help="Skip updating mods data and upload all downloaded archives that haven't already. Default: false",
)
parser.add_option(
    "-c",
    "--check",
    action="store_true",
    dest="check_sha",
    help="Needs to be implemented! Check downloaded archives. Default: false",
)
parser.add_option(
    "-d",
    "--directory",
    dest="dir",
    default="data",
    help="write data to FOLDER",
    metavar="FOLDER",
)
parser.add_option(
    "-e",
    "--email",
    dest="email",
    default="",
    help="GSuite drive email to upload to",
    metavar="EMAIL",
)
parser.add_option(
    "-f",
    "--flush",
    action="store_false",
    default=True,
    dest="flush",
    help="Turn off screen output flush",
)
parser.add_option(
    "--keep-important",
    action="store_false",
    default=True,
    dest="keep_important",
    help="Only flush non important lines.",
)
parser.add_option(
    "-p",
    "--password",
    dest="password",
    default="",
    help="RClone configuration password",
    metavar="PASSWORD",
)
parser.add_option(
    "-t",
    "--token",
    dest="token",
    default="",
    help="sets the token to download with",
    metavar="TOKEN",
)
parser.add_option(
    "-u",
    "--user",
    dest="user",
    default="",
    help="sets the user name to download with",
    metavar="USER",
)
parser.add_option(
    "-U",
    "--upload",
    action="store_true",
    dest="upload",
    help="Upload all downloaded archives. Default: false",
)

(options, args) = parser.parse_args()

columns, _ = os.get_terminal_size()

if options.user == "" or options.token == "":
    print("Set --user USER and --token TOKEN")
    exit(1)

if (options.upload or options.upload_all) and (options.email == "" or options.password == ""):
    print("When supplying --upload you need to supply --email EMAIL and --password PASSWORD")
    exit(1)

# if GSuite email and password are supplied guess to upload archives
if options.email or options.password:
    options.upload = True

if options.flush:
    print_end = "\r"
else:
    print_end = "\r\n"


def print_progress(out, important = True):
    if important and options.keep_important:
        print("{}{}".format(out, " " * (columns - len(out))), end="\r\n", flush=options.flush)
    else:
        print("{}{}".format(out, " " * (columns - len(out))), end=print_end, flush=options.flush)


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

# reuse local data
if options.upload_all:
    if os.path.exists(data_file):
        with open(data_file, "r") as f:
            data = json.load(f)
        with open(mods_cache_file, "r") as f:
            mods = json.load(f)
    else:
        logging.error("No data.json found.")
        exit(1)
else:
    mods_req = requests.get("https://mods.factorio.com/api/mods?page_size=max")
    if mods_req.status_code != 200:
        logging.warning(mods_req.prepare())
        exit(1)

    mods = mods_req.json()
    with open(mods_file, "w") as f:
        json.dump(mods, f, indent=2, sort_keys=True)


mod_count = len(mods["results"])

for i, mod in enumerate(mods["results"]):
    # print_progress("Processing mod {} of {}: Comparing versions of {}".format(i, mod_count, mod["name"]))

    mod_folder = "{}/{}".format(options.dir, mod["name"])
    if not os.path.isdir(mod_folder):
        os.makedirs(mod_folder, exist_ok=True)

    # mod was processed before
    if mod["name"] in data:
        versions = []
        for k in data[mod["name"]]["releases"]:
            versions.append(data[mod["name"]]["releases"][k]["version"])

        if not (options.check_sha or options.upload_all or options.check_all):
            if mod["latest_release"]["version"] in versions:
                continue

    # data entry empty, mod new then process all archives
    else:
        data[mod["name"]] = {}
        data[mod["name"]]["releases"] = {}

    # update archives
    print_progress("Processing mod {} of {}: Getting data for {}".format(i + 1, mod_count, mod["name"]), False)
    mod_data_req = requests.get("https://mods.factorio.com/api/mods/{}/full".format(mod["name"]))

    if mod_data_req.status_code != 200:
        logging.error(mods_req.prepare())
        exit(1)

    mod_data = mod_data_req.json()
    with open("{}/mod.json".format(mod_folder), "w") as f:
        json.dump(mod_data, f, indent=2, sort_keys=True)

    for j, release in enumerate(mod_data["releases"]):
        release_id = release["download_url"].split("/")[3]

        if release_id not in data[mod["name"]]["releases"]:
            data[mod["name"]]["releases"][release_id] = {}
        else:
            if not options.check_sha and not options.upload_all:
                continue

        archive = data[mod["name"]]["releases"][release_id]
        archive["file_name"] = release["file_name"]
        archive["sha1"] = release["sha1"]
        archive["version"] = release["version"]

        # add uploaded tag if necessary
        if "uploaded" not in archive:
            archive["uploaded"] = False
        else:
            continue

        # download files
        if not (options.check_sha or options.upload_all):
            print_progress("Processing mod {} of {}: Downloading {}".format(i + 1, mod_count, archive["file_name"]))

            url = "https://mods.factorio.com{}?username={}&token={}".format(release["download_url"],
                                                                            options.user, options.token)
            p = Popen(["curl", "-Ls", url, "-o", "{}/{}".format(mod_folder, archive["file_name"])])
            output = p.communicate()[0]

            if p.returncode != 0:
                logging.error("Couldn't download %s/%s", mod["name"], archive["file_name"])

        # write sha1 file
        sha1_file = "{}.sha1".format(os.path.splitext(archive["file_name"])[0])
        with open("{}/{}".format(mod_folder, sha1_file), "w", newline="\n") as f:
            f.write("{}  ./{}\n".format(archive["sha1"], archive["file_name"]))

        # check sha1
        p = Popen(["sha1sum", "-c", "./{}".format(sha1_file)], cwd=mod_folder, stdout=PIPE)
        output = p.communicate()[0]
        if p.returncode != 0:
            logging.warning("sha1 mismatch at %s/%s", mod["name"], archive["file_name"])

        # upload to gsuite
        if options.upload:
            upload_errors = False
            for file in [archive["file_name"], sha1_file]:
                out = "Processing mod {} of {}: Uploading {}".format(
                    i + 1, mod_count, archive["file_name"]
                )
                print("{}{}".format(out, " " * (columns - len(out))), end=print_end, flush=options.flush)

                p = Popen(
                    [
                        "rclone",
                        "--drive-impersonate",
                        options.email,
                        "--retries",
                        "3",
                        "--retries-sleep",
                        "3s",
                        "move",
                        "./{}".format(file),
                        "gdrive:/archive/factorio-mods/{}".format(mod["name"]),
                    ],
                    cwd=mod_folder,
                    env={
                        "HOME": os.environ["HOME"],
                        "RCLONE_CONFIG_PASS": options.password,
                    },
                    stdout=PIPE,
                )
                output = p.communicate()[0]

                if p.returncode != 0:
                    upload_errors = True
                    logging.error(
                        "Upload of file %s from mod %s failed",
                        archive["file_name"],
                        mod["name"],
                    )

                if output.decode("utf-8").isspace():
                    upload_errors = True
                    logging.error("Possible error occurred:")
                    logging.error(output.decode("utf-8"))

            if not upload_errors:
                archive["uploaded"] = True

    with DelayedKeyboardInterrupt():
        with open(data_file, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)

if os.path.exists(mods_cache_file):
    os.remove(mods_cache_file)
