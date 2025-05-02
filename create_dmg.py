#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的DMG创建脚本 - 在正确的conda环境中运行
"""

import os
import sys
import subprocess
import tempfile
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

def create_background_image():
    """创建DMG背景图像，显示拖拽安装指示"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # 创建临时目录存放背景图像
        background_dir = PROJECT_ROOT / "build/dmg_background"
        background_dir.mkdir(parents=True, exist_ok=True)
        background_path = background_dir / "background.png"
        
        # 创建背景图像
        width, height = 600, 400
        image = Image.new('RGBA', (width, height), (240, 240, 240, 255))
        draw = ImageDraw.Draw(image)
        
        # 尝试使用系统字体
        try:
            # macOS系统字体
            font_large = ImageFont.truetype("/System/Library/Fonts/STHeiti Light.ttc", 24)
            font_small = ImageFont.truetype("/System/Library/Fonts/STHeiti Light.ttc", 16)
        except:
            # 使用默认字体
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # 绘制标题
        title = f"Install {APP_NAME}"
        draw.text((width/2, 50), title, fill=(0, 0, 0, 255), font=font_large, anchor="mm")
        
        # 绘制图标位置指示
        draw.ellipse((150-50, 200-50, 150+50, 200+50), outline=(100, 100, 100, 128), width=2)
        
        # 绘制Applications文件夹位置指示
        draw.ellipse((450-50, 200-50, 450+50, 200+50), outline=(100, 100, 100, 128), width=2)
        
        # 绘制箭头
        arrow_points = [(220, 200), (380, 200), (350, 180), (380, 200), (350, 220)]
        draw.line(arrow_points, fill=(0, 0, 0, 200), width=3)
        
        # 绘制说明文字
        instructions = "Drag to Applications folder to install"
        draw.text((width/2, 300), instructions, fill=(0, 0, 0, 255), font=font_small, anchor="mm")
        
        # 保存背景图像
        image.save(background_path)
        return background_path
        
    except Exception as e:
        print(f"创建背景图像失败: {e}")
        return None

def create_dmg():
    """创建DMG安装包"""
    app_path = DIST_DIR / APP_BUNDLE_NAME
    
    if not app_path.exists():
        print(f"错误: 应用程序不存在: {app_path}")
        return False
    
    try:
        # 创建临时DMG构建目录
        dmg_build_dir = PROJECT_ROOT / "build/dmg"
        if dmg_build_dir.exists():
            import shutil
            shutil.rmtree(dmg_build_dir)
        os.makedirs(dmg_build_dir, exist_ok=True)
        
        # 复制应用程序到构建目录
        print(f"复制应用程序到构建目录...")
        dmg_app_path = dmg_build_dir / APP_BUNDLE_NAME
        subprocess.run(["cp", "-R", str(app_path), str(dmg_app_path)], check=True)
        
        # 创建Applications文件夹链接
        print(f"创建Applications文件夹链接...")
        applications_link = dmg_build_dir / "Applications"
        os.symlink("/Applications", applications_link)
        
        # 创建背景图像
        background_path = create_background_image()
        has_background = background_path is not None
        
        if has_background:
            # 创建背景图像目录
            background_dir = dmg_build_dir / ".background"
            os.makedirs(background_dir, exist_ok=True)
            
            # 复制背景图像
            subprocess.run(["cp", str(background_path), str(background_dir / "background.png")], check=True)
        
        # 创建临时DMG
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
            "-srcfolder", str(dmg_build_dir),
            "-ov", "-format", "UDRW",
            str(temp_dmg)
        ], check=True)
        
        # 挂载临时DMG
        print("挂载临时DMG...")
        mount_point = f"/Volumes/{APP_NAME}"
        # 如果已经挂载，先卸载
        if os.path.exists(mount_point):
            subprocess.run(["hdiutil", "detach", mount_point, "-force"], check=False)
            
        subprocess.run(["hdiutil", "attach", str(temp_dmg), "-readwrite"], check=True)
        
        # 设置DMG外观
        if has_background:
            print("设置DMG外观...")
            # 创建临时AppleScript文件
            applescript = f"""
            tell application "Finder"
                tell disk "{APP_NAME}"
                    open
                    set current view of container window to icon view
                    set toolbar visible of container window to false
                    set statusbar visible of container window to false
                    set the bounds of container window to {{100, 100, 700, 500}}
                    set theViewOptions to the icon view options of container window
                    set arrangement of theViewOptions to not arranged
                    set icon size of theViewOptions to 80
                    set background picture of theViewOptions to file ".background:background.png"
                    set position of item "{APP_BUNDLE_NAME}" of container window to {{150, 200}}
                    set position of item "Applications" of container window to {{450, 200}}
                    update without registering applications
                    delay 3
                    close
                end tell
            end tell
            """
            
            with tempfile.NamedTemporaryFile(suffix=".applescript", delete=False) as script_file:
                script_file.write(applescript.encode("utf-8"))
                script_path = script_file.name
                
            try:
                subprocess.run(["osascript", script_path], check=True)
            except Exception as e:
                print(f"设置DMG外观失败: {e}")
            finally:
                os.unlink(script_path)
        
        # 卸载临时DMG
        print("卸载临时DMG...")
        subprocess.run(["hdiutil", "detach", mount_point], check=False)
        # 如果无法卸载，强制卸载
        if os.path.exists(mount_point):
            subprocess.run(["hdiutil", "detach", mount_point, "-force"], check=False)
        
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