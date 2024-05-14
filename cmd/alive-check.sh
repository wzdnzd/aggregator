#!/bin/bash

# clash path
current=$(cd "$(dirname "$0")";pwd)
clash_path="${current%/*}/clash"

# change workspace
cd ${clash_path}

bin_name="clash-linux"

# executable
chmod +x ${bin_name}

# subscribe array
content=$(curl -L --retry 5 --retry-delay 1 "subscribes url")
subscribes=($content)

# startup and speedtest
for subscribe in "${subscribes[@]}"
do
  # delete config.yaml if exists
  rm -rf config.yaml

  # intercept the right part of the string %2F
  token=${subscribe##*%2F}

  # intercept the first 16 characters
  token=${token:0:16}

  echo "start check subscribes alive, subscribe: ${token}"
  
  # config
  wget -q -t 2 "https://sub.xeton.dev/sub?target=clash&url=$subscribe&insert=false&emoji=true&list=false&udp=true&tfo=false&expand=true&scv=false&fdn=true&new_name=true&filename=config.yaml" -O config.yaml

  if [ $? -ne 0 ]; then
      echo "download config file error, subscribe: ${token}"
      continue
  fi

  # startup
  nohup ./${bin_name} -d . -f config.yaml &

  if [ $? -ne 0 ]; then
      echo "startup clash failed, subscribe: ${token}"
      cat config.yaml
      continue
  fi

  # wait a monment
  sleep 2.5

  # set system proxy
  export http_proxy=http://127.0.0.1:7890
  export https_proxy=http://127.0.0.1:7890

  # google
  for((i=1;i<=3;i++))
  do
    curl --connect-timeout 6 -m 10 "https://www.youtube.com" >/dev/null 2>&1
    curl --connect-timeout 6 -m 10 "https://www.google.com" >/dev/null 2>&1
  done

  # # speedtest  
  wget -q --timeout=10 -t 2 --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.66 Safari/537.36 Edg/103.0.1264.44" "https://cachefly.cachefly.net/10mb.test" -O 10mb.test

  if [ $? -ne 0 ]; then
      echo "download file 10mb.test failed, subscribe: ${token}"
  fi

  # unset proxy
  unset http_proxy
  unset https_proxy

  # clear
  rm -rf ./10mb.test

  # close clash
  pkill -9 ${bin_name}
done

exit 0