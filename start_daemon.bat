@echo off
cd /d %~dp0
python main.py --list-daemon --interval=60
