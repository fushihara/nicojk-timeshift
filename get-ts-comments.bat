:@echo off
:sjis
setlocal
cd /D %~dp0

python ./get-new-jikkyo-comments.py ts --databaseDir ".\new-nico-jikkyo-logs" --jkDir "./jk-txt" %*
pause
