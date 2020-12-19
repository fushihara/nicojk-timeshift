:@echo off
:sjis
setlocal
cd /D %~dp0

python ./get-new-jikkyo-comments.py ts -j "jk-txt" %*
pause
