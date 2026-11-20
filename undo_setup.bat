@echo off
rem Removes what setup.bat added (the MCP server, its name in conf.yaml and the rules in your persona).
call "%~dp0setup.bat" --undo
