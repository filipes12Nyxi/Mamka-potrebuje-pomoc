
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import threading
import serial
import time
import winsound
import wave
import io

# ==================================
# NASTAVENI
# ==================================

PORT_ARDUINO = "COM7"
RYCHLOST = 9600
PORT_WEB = 8000

SLOZKA = Path(__file__).resolve().parent
SLOZKA_ZVUKU = SLOZKA / "zvuky"

POVOLENE_ZVUKY = {
    "start.wav",
    "stop.wav",
    "modry_kod.wav"
}

MAX_VELIKOST = 20 * 1024 * 1024

arduino = None
zamek = threading.Lock()


# ==================================
# ARDUINO
# ==================================

def pripoj_arduino():
    global arduino

    if arduino is None or not arduino.is_open:
        arduino = serial.Serial(
            PORT_ARDUINO,
            RYCHLOST,
            timeout=1
        )

        # Arduino se po pripojeni restartuje.
        time.sleep(2)
        arduino.reset_input_buffer()

        print("Arduino pripojeno.")

    return arduino


def posli_arduinu(prikaz):
    with zamek:
        zarizeni = pripoj_arduino()
        zarizeni.write((prikaz + "\n").encode("utf-8"))
        zarizeni.flush()


# ==================================
# ZVUKY
# ==================================

def prehrat_zvuk(nazev):
    if nazev not in POVOLENE_ZVUKY:
        return

    soubor = SLOZKA_ZVUKU / nazev

    if not soubor.exists():
        print("Zvuk zatim neexistuje:", nazev)
        return

    try:
        winsound.PlaySound(
            str(soubor),
            winsound.SND_FILENAME |
            winsound.SND_ASYNC |
            winsound.SND_NODEFAULT
        )

        print("Prehravam:", nazev)

    except Exception as chyba:
        print("Chyba prehravani:", chyba)


def uloz_zvuk(nazev, obsah):
    if nazev not in POVOLENE_ZVUKY:
        raise ValueError("Nepovoleny nazev souboru.")

    if len(obsah) == 0 or len(obsah) > MAX_VELIKOST:
        raise ValueError("Neplatna velikost nahravky.")

    # Kontrola, ze jde o platny WAV.
    with wave.open(io.BytesIO(obsah), "rb") as zvuk:
        if zvuk.getnchannels() != 1:
            raise ValueError("Nahravka musi byt mono.")

        if zvuk.getsampwidth() != 2:
            raise ValueError("Nahravka musi mit 16bitovy zvuk.")

        if zvuk.getcomptype() != "NONE":
            raise ValueError("Nepodporovany format zvuku.")

        if zvuk.getnframes() == 0:
            raise ValueError("Prazdna nahravka.")

    SLOZKA_ZVUKU.mkdir(exist_ok=True)

    cesta = SLOZKA_ZVUKU / nazev
    cesta.write_bytes(obsah)

    print("Ulozen zvuk:", cesta)


# ==================================
# WEBOVY SERVER
# ==================================

class Server(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            soubor = SLOZKA / "index.html"

            if not soubor.exists():
                self.send_error(404, "Chybi index.html")
                return

            obsah = soubor.read_bytes()

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )
            self.send_header(
                "Content-Length",
                str(len(obsah))
            )
            self.end_headers()
            self.wfile.write(obsah)

        else:
            self.send_error(404)

    def do_POST(self):

        # --------------------------
        # PRIJEM HLASOVE NAHRAVKY
        # --------------------------

        if self.path.startswith("/api/audio?"):
            try:
                adresa = urlparse(self.path)
                parametry = parse_qs(adresa.query)

                nazev = parametry.get("name", [""])[0]

                if nazev not in POVOLENE_ZVUKY:
                    self.send_error(400, "Neplatny nazev zvuku.")
                    return

                delka = int(self.headers.get("Content-Length", 0))

                if delka <= 0 or delka > MAX_VELIKOST:
                    self.send_error(400, "Neplatna velikost souboru.")
                    return

                obsah = self.rfile.read(delka)

                if len(obsah) != delka:
                    self.send_error(400, "Neuplny soubor.")
                    return

                uloz_zvuk(nazev, obsah)

                self.odeslat(200, {
                    "ok": True,
                    "message": "Nahravka ulozena.",
                    "file": nazev
                })

            except Exception as chyba:
                print("CHYBA NAHRAVKY:", chyba)

                self.odeslat(400, {
                    "ok": False,
                    "error": str(chyba)
                })

            return

        # --------------------------
        # OVLADANI ARDUINA
        # --------------------------

        if self.path != "/api/command":
            self.send_error(404)
            return

        try:
            delka = int(self.headers.get("Content-Length", 0))

            if delka <= 0 or delka > 10000:
                self.send_error(400)
                return

            data = json.loads(self.rfile.read(delka))
            prikaz = data.get("command")

            if prikaz not in ("START", "STOP", "MODRY_KOD"):
                self.send_error(400, "Neznamy prikaz.")
                return

            if prikaz in ("START", "STOP"):
                posli_arduinu(prikaz)

            # Prehrani hlasove zpravy pres pocitac.
            zvuky = {
                "START": "start.wav",
                "STOP": "stop.wav",
                "MODRY_KOD": "modry_kod.wav"
            }

            prehrat_zvuk(zvuky[prikaz])

            self.odeslat(200, {
                "ok": True,
                "command": prikaz
            })

        except Exception as chyba:
            print("CHYBA:", chyba)

            self.odeslat(503, {
                "ok": False,
                "error": str(chyba)
            })

    def odeslat(self, kod, data):
        obsah = json.dumps(data).encode("utf-8")

        self.send_response(kod)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(obsah))
        )
        self.end_headers()
        self.wfile.write(obsah)

    def log_message(self, format, *args):
        print(format % args)


# ==================================
# SPUSTENI
# ==================================

print("================================")
print(" MAMKA POTREBUJE POMOC")
print("================================")
print("Arduino:", PORT_ARDUINO)
print("Webovy port:", PORT_WEB)
print("Slozka zvuku:", SLOZKA_ZVUKU)
print("Spoustim prijimac...")

SLOZKA_ZVUKU.mkdir(exist_ok=True)

server = ThreadingHTTPServer(
    ("0.0.0.0", PORT_WEB),
    Server
)

print("Prijimac je pripraven.")
print("Server bezi. Ukonceni: CTRL + C")

try:
    server.serve_forever()

except KeyboardInterrupt:
    print("Ukoncuji server...")

finally:
    server.server_close()

    if arduino is not None and arduino.is_open:
        arduino.close()

    print("Server ukoncen.")
