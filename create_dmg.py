#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的DMG创建脚本 - 在正确的conda环境中运行
"""

import os
import sys
import subprocess
from pathlib import Path

# 获取路径
PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
APP_NAME = "UCI-ClusterManager"
APP_VERSION = "0.0.1"  # 应与updater.py中的版本一致
APP_BUNDLE_NAME = f"{APP_NAME}.app"
DIST_DIR = PROJECT_ROOT / "dist"
DMG_NAME = f"{APP_NAME}-{APP_VERSION}-macos.dmg"
OUTPUT_DMG = PROJECT_ROOT / DMG_NAME

# 打印调试信息
print(f"项目根目录: {PROJECT_ROOT}")
print(f"应用包路径: {DIST_DIR / APP_BUNDLE_NAME}")
print(f"APP包是否存在: {(DIST_DIR / APP_BUNDLE_NAME).exists()}")

def create_dmg():
    """创建DMG安装包"""
    app_path = DIST_DIR / APP_BUNDLE_NAME
    
    if not app_path.exists():
        print(f"错误: 应用程序不存在: {app_path}")
        return False
    
    try:
        # 临时DMG文件
        temp_dmg = PROJECT_ROOT / f"{APP_NAME}-temp.dmg"
        
        # 删除可能存在的旧文件
        if temp_dmg.exists():
            os.remove(temp_dmg)
        if OUTPUT_DMG.exists():
            os.remove(OUTPUT_DMG)
        
        print(f"创建临时DMG: {temp_dmg}")
        subprocess.run([
            "hdiutil", "create",
            "-volname", APP_NAME,
            "-srcfolder", str(app_path),
            "-ov", "-format", "UDRW",
            str(temp_dmg)
        ], check=True)
        
        print(f"转换为只读DMG: {OUTPUT_DMG}")
        subprocess.run([
            "hdiutil", "convert",
            str(temp_dmg),
            "-format", "UDZO",
            "-o", str(OUTPUT_DMG)
        ], check=True)
        
        # 清理临时文件
        os.remove(temp_dmg)
        
        print(f"DMG创建成功: {OUTPUT_DMG}")
        return True
    except Exception as e:
        print(f"创建DMG时出错: {e}")
        return False

if __name__ == "__main__":
    print("开始创建DMG安装包...")
    if create_dmg():
        print("DMG创建成功!")
        sys.exit(0)
    else:
        print("DMG创建失败!")
        sys.exit(1) 