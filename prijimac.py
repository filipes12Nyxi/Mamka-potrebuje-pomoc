
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import json
import threading
import serial

# Nastavení
PORT_ARDUINO = "COM7"
RYCHLOST = 9600
PORT_WEB = 8000

arduino = None
zamek = threading.Lock()


def pripoj_arduino():
    global arduino

    if arduino is None or not arduino.is_open:
        arduino = serial.Serial(
            PORT_ARDUINO,
            RYCHLOST,
            timeout=1
        )

    return arduino


class Server(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            soubor = Path(__file__).with_name("index.html")
            obsah = soubor.read_bytes()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(obsah)))
            self.end_headers()
            self.wfile.write(obsah)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/command":
            self.send_error(404)
            return

        delka = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(delka))
        prikaz = data.get("command")

        if prikaz not in ("START", "STOP", "MODRY_KOD"):
            self.send_error(400)
            return

        if prikaz == "MODRY_KOD":
            self.odeslat(501, {
                "error": "Modry kod bude doplnen pozdeji."
            })
            return

        try:
            with zamek:
                zarizeni = pripoj_arduino()
                zarizeni.write((prikaz + "\n").encode("utf-8"))

            self.odeslat(200, {
                "ok": True,
                "command": prikaz
            })

        except Exception as chyba:
            self.odeslat(503, {
                "error": str(chyba)
            })

    def odeslat(self, kod, data):
        obsah = json.dumps(data).encode("utf-8")

        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(obsah)))
        self.end_headers()
        self.wfile.write(obsah)

    def log_message(self, format, *args):
        print(format % args)


print("DOMACI OVLADANI")
print("Adresa: http://IP-POCITACE:8000")
print("Server se spousti...")

server = ThreadingHTTPServer(("0.0.0.0", PORT_WEB), Server)
server.serve_forever()

