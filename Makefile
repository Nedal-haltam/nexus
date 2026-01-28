.PHONY: server client publish-client publish-server

PYINSTALLER := c:\users\lenovo\appdata\local\packages\pythonsoftwarefoundation.python.3.13_qbz5n2kfra8p0\localcache\local-packages\python313\scripts\pyinstaller.exe

client:
	python3.13.exe .\src\main.py
server:
	python3.13.exe .\src\server.py

publish-client:
	$(PYINSTALLER) --exclude-module PyQt6 --collect-all ultralytics --collect-all clip --collect-all pandas --onefile --name nexus_client .\src\main.py
publish-server:
	$(PYINSTALLER) --exclude-module PyQt6 --collect-all ultralytics --collect-all clip --collect-all pandas --onefile --name nexus_server .\src\server.py

ssl-setup:
	openssl.exe req -x509 -nodes -days 365 -newkey rsa:4096 -keyout ".\ssl-files\server.key" -out ".\ssl-files\server.crt" -config "./ssl-files/san.cnf"
