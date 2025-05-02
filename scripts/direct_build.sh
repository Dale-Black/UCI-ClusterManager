#!/bin/bash
# 直接构建脚本，简化流程

set -e  # 出错时停止

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

echo "脚本目录: $SCRIPT_DIR"
echo "项目根目录: $PROJECT_ROOT"
echo "当前目录: $(pwd)"

# 确保在项目根目录工作
cd "$PROJECT_ROOT"
echo "工作目录: $(pwd)"

# 激活conda环境
echo "激活conda环境hpc_env..."
source $(conda info --base)/etc/profile.d/conda.sh
conda activate hpc_env
echo "Python路径: $(which python)"
echo "Python版本: $(python --version)"

# 查看重要目录
echo "检查my_hpc_app目录:"
ls -la "$PROJECT_ROOT/my_hpc_app"

# 确认main.py是否存在
if [ -f "$PROJECT_ROOT/my_hpc_app/main.py" ]; then
    echo "main.py文件存在"
else
    echo "main.py文件不存在！"
    exit 1
fi

# 清理构建文件
echo "清理构建文件..."
rm -rf dist build

# 直接运行pyinstaller，显式包含所有需要的模块
echo "开始构建..."
python -m PyInstaller --name="UCI-ClusterManager" \
    --windowed \
    --add-data="$PROJECT_ROOT/my_hpc_app/resources:resources" \
    --add-data="$PROJECT_ROOT/my_hpc_app/modules:modules" \
    --add-data="$PROJECT_ROOT/my_hpc_app/ui:ui" \
    --hidden-import=pexpect \
    --hidden-import=paramiko \
    --hidden-import=cryptography \
    --hidden-import=bcrypt \
    --hidden-import=PyQt5 \
    --hidden-import=PyQt5.QtWidgets \
    --hidden-import=PyQt5.QtCore \
    --hidden-import=PyQt5.QtGui \
    --hidden-import=requests \
    --hidden-import=packaging \
    --hidden-import=packaging.version \
    --hidden-import=json \
    --hidden-import=os \
    --hidden-import=sys \
    --hidden-import=time \
    --hidden-import=logging \
    --hidden-import=subprocess \
    --hidden-import=datetime \
    --icon="$PROJECT_ROOT/my_hpc_app/resources/icon.ico" \
    --osx-bundle-identifier="edu.uci.clustermanager" \
    "$PROJECT_ROOT/my_hpc_app/main.py"

# 检查构建结果
if [ -d "$PROJECT_ROOT/dist/UCI-ClusterManager.app" ]; then
    echo "构建成功！应用位于: $PROJECT_ROOT/dist/UCI-ClusterManager.app"
else
    echo "构建失败！"
    exit 1
fi 