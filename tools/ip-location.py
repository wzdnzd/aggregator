# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-12-14

import argparse
import os
import re
import shutil
import zipfile

import pandas as pd
import requests
from geoip2 import database

DATA_DIR = os.path.abspath(os.path.dirname(__file__))


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def extract_reverse_ips(base: str, update: bool = False, retry: int = 3) -> list[str]:
    base, directoy = trim(base), "output"
    if not base:
        raise ValueError("invalid directory name")

    last = os.path.join(base, "all.txt")

    # read from merged file if exists
    if not update and os.path.exists(last) and os.path.isfile(last):
        with open(last, "r", encoding="UTF8") as f:
            return [trim(line.replace("\n", "")) for line in f.readlines() if line]

    fullpath = os.path.join(base, directoy)
    if os.path.exists(fullpath) and os.path.isdir(fullpath):
        # remove old directory
        shutil.rmtree(fullpath)

    # download zip file
    url, filename = "https://zip.baipiao.eu.org", "ips.zip"
    download(url, base, filename, retry, 30)

    filepath = os.path.join(base, filename)
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        raise Exception(f"cannot download zip file from {url} to {filepath}")

    # extract zip file
    with zipfile.ZipFile(filepath, "r") as f:
        f.extractall(fullpath)

    # traverse and merge all files
    texts = set()
    for file in os.listdir(fullpath):
        if not file.endswith(".txt"):
            continue

        with open(os.path.join(fullpath, file), "r", encoding="UTF8") as f:
            for line in f.readlines():
                line = trim(line).replace("\n", "")
                if re.match(r"\d+\.\d+\.\d+\.\d+", line):
                    texts.add(line)

    if not texts:
        print("no valid ip found in all files")
        return []

    # write merged file
    with open(last, "w", encoding="UTF8") as f:
        content = "\n".join(texts)
        f.write(content)
        f.flush()

    # remove directory and zip file
    shutil.rmtree(fullpath)
    os.remove(filepath)

    return list(texts)


def download_mmdb(target: str, filepath: str, retry: int = 3):
    """
    Download GeoLite2-City.mmdb from github release
    """

    target = trim(target)
    if not target:
        raise ValueError("invalid download target")

    # extract download url from github release page
    release_api = "https://api.github.com/repos/PrxyHunter/GeoLite2/releases/latest?per_page=1"

    count, response = 0, None
    while count < retry and response is None:
        try:
            response = requests.get(release_api, timeout=10)
        except Exception:
            count += 1

    if not response or response.status_code != 200:
        raise Exception("request github release api failed")

    assets = response.json().get("assets", [])
    if not assets:
        raise Exception("no assets found in github release")

    download_url = ""
    for asset in assets:
        if asset.get("name", "") == target:
            download_url = asset.get("browser_download_url", "")
            break

    if not download_url:
        raise Exception("no download url found in github release")

    download(download_url, filepath, target, retry, 60)


def download(url: str, filepath: str, filename: str, retry: int = 3, timeout: int = 10) -> None:
    """Download file from url to filepath with filename"""

    if retry < 0:
        raise Exception("archieved max retry count for download")

    url = trim(url)
    if not url:
        raise ValueError("invalid download url")

    filepath = trim(filepath)
    if not filepath:
        raise ValueError("invalid save filepath")

    filename = trim(filename)
    if not filename:
        raise ValueError("invalid save filename")

    if not os.path.exists(filepath) or not os.path.isdir(filepath):
        os.makedirs(filepath)

    fullpath = os.path.join(filepath, filename)
    if os.path.exists(fullpath) and os.path.isfile(fullpath):
        os.remove(fullpath)

    # download target file from github release to fullpath
    timeout = max(timeout, 6)
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(fullpath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    f.flush()
    except Exception:
        return download(url, filepath, filename, retry - 1, min(timeout * 2, 180))

    print(f"download file {filename} to {fullpath} success")


def load_mmdb(directory: str, filename: str, update: bool = False) -> None:
    filepath = os.path.join(directory, filename)
    if update or not os.path.exists(filepath) or not os.path.isfile(filepath):
        download_mmdb(filename, directory)

    return database.Reader(filepath)


def main(args: argparse.Namespace) -> None:
    base = trim(args.directory)
    if not base:
        raise ValueError("please specify a valid workspace directory")

    filename = trim(args.file)
    if not filename:
        raise ValueError("please specify a valid output filename")

    # get reverse ip data first
    ips = extract_reverse_ips(base, args.update)
    print(f"got {len(ips)} reverse ip for cloudflare")

    if not ips:
        return

    df = pd.DataFrame(columns=["IP", "国家", "州/区", "城市", "注册地", "ASN", "ORG"])
    try:
        # load city mmdb and query ip location
        reader = load_mmdb(base, "GeoLite2-City.mmdb", args.update)
        for ip in ips:
            try:
                response = reader.city(ip)
            except Exception:
                continue

            country = response.country.names.get("zh-CN", "")
            subdivision = response.subdivisions.most_specific.names.get("zh-CN", "")
            city = response.city.names.get("zh-CN", "")
            register = response.registered_country.names.get("zh-CN", "")

            # append to dataframe
            df.loc[len(df)] = [ip, country, subdivision, city, register, "", ""]
    except Exception as e:
        raise e
    finally:
        reader.close()

    try:
        # load ans mmdb and query ip organization
        reader = load_mmdb(base, "GeoLite2-ASN.mmdb", args.update)
        for index, row in df.iterrows():
            try:
                response = reader.asn(row["IP"])
            except Exception:
                continue

            df.loc[index, "ASN"] = response.autonomous_system_number
            df.loc[index, "ORG"] = response.autonomous_system_organization
    except Exception as e:
        raise e
    finally:
        reader.close()

    # save to excel file
    filepath = os.path.join(base, filename)
    df.to_excel(filepath, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-d",
        "--directory",
        type=str,
        required=False,
        default=os.path.join(DATA_DIR, "data"),
        metavar="",
        help="data directory",
    )

    parser.add_argument(
        "-f",
        "--file",
        type=str,
        required=False,
        default="ips.xlsx",
        metavar="",
        help="ip with location filename",
    )

    parser.add_argument(
        "-u",
        "--update",
        dest="update",
        action="store_true",
        help="force update ip and mmdb file",
    )

    main(parser.parse_args())
