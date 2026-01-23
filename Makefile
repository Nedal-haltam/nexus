.PHONY: server client publish-client publish-server

PYINSTALLER := c:\users\lenovo\appdata\local\packages\pythonsoftwarefoundation.python.3.13_qbz5n2kfra8p0\localcache\local-packages\python313\scripts\PYINSTALLER.exe

client:
	python3.13.exe .\src\main.py
server:
	python3.13.exe .\src\server.py

publish-client:
	$(PYINSTALLER) --exclude-module PyQt6 --onefile --name nexus_client .\src\main.py
publish-server:
	$(PYINSTALLER) --exclude-module PyQt6 --onefile --name nexus_server .\src\server.py
