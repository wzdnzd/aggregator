#!/bin/bash

# 设置目标文件名和路径
TARGET_FILE="start.sh"
TARGET_PATH="/aggregator"
SOURCE_FILE="/aggregator/default_start.sh"

# 检查目标路径中是否存在特定文件
if [ ! -f "$TARGET_PATH/$TARGET_FILE" ]; then
    echo "$TARGET_FILE does not exist in $TARGET_PATH, copying default script..."
    # 如果文件不存在，则复制并重命名
    cp "$SOURCE_FILE" "$TARGET_PATH/$TARGET_FILE"
else
    echo "$TARGET_FILE already exists in $TARGET_PATH, skipping copy operation."
fi

#!/bin/bash

# 读取环境变量中的执行时间参数
TIME_COLLECT=${EXECUTION_TIME_COLLECT:-"0 1 * * *"}  # 默认每天1点执行
TIME_PROCESS=${EXECUTION_TIME_PROCESS:-"0 2 */2 * *"}  # 默认每2天2点执行

# 创建日志文件
mkdir -p /log

# 设置日志文件路径
LOG_FILE_COLLECT="/log/collect.log"
LOG_FILE_PROCESS="/log/process.log"

# 定义要执行的命令
COMMAND_COLLECT="/usr/local/bin/python -u /aggregator/subscribe/collect.py --all --overwrite --skip"
COMMAND_PROCESS="/usr/local/bin/python -u /aggregator/subscribe/process.py --all --overwrite --skip"

# 立即执行命令
echo "Executing collect.py immediately..."
"python -u subscribe/collect.py --all --overwrite --skip" >> $LOG_FILE_COLLECT 2>&1

echo "Executing process.py immediately..."
"python -u subscribe/collect.py --all --overwrite --skip" >> $LOG_FILE_PROCESS 2>&1

# 添加cron任务
echo "$TIME_COLLECT $COMMAND_COLLECT >> $LOG_FILE_COLLECT 2>&1" > /etc/cron.d/aggregator-cron
echo "$TIME_PROCESS $COMMAND_PROCESS >> $LOG_FILE_PROCESS 2>&1" >> /etc/cron.d/aggregator-cron


chmod 0644 /etc/cron.d/aggregator-cron
crontab /etc/cron.d/aggregator-cron

# (crontab -l 2>/dev/null; 
#   echo "$TIME_COLLECT $COMMAND_COLLECT >> $LOG_FILE_COLLECT 2>&1";
#   echo "$TIME_PROCESS $COMMAND_PROCESS >> $LOG_FILE_PROCESS 2>&1") | crontab -

# 启动cron服务
service cron start

# 保持容器运行
tail -f /dev/null