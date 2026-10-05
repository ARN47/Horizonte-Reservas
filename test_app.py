"""Pruebas automáticas. Ejecutar: python -m unittest -v"""
import os, tempfile, unittest
from datetime import date, timedelta

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
import app as miapp  # noqa: E402

FUTURA = (date.today() + timedelta(days=3)).isoformat()


class Pruebas(unittest.TestCase):
    def setUp(self):
        if os.path.exists(miapp.app.config["DB_PATH"]):
            os.remove(miapp.app.config["DB_PATH"])
        miapp.init_db()

    def cliente(self, usuario, clave):
        c = miapp.app.test_client()
        r = c.post("/api/login", json={"usuario": usuario, "clave": clave})
        self.assertEqual(r.status_code, 200)
        return c

    def pedir(self, c, recurso=1, fecha=FUTURA, modulo=1):
        return c.post("/api/solicitudes", json={"recurso_id": recurso, "fecha": fecha, "modulo": modulo})

    def test_01_solicitud_valida_queda_pendiente(self):
        r = self.pedir(self.cliente("ana", "ana123"))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["estado"], "PENDIENTE")

    def test_02_datos_invalidos(self):
        c = self.cliente("ana", "ana123")
        self.assertEqual(self.pedir(c, fecha="").status_code, 400)
        self.assertEqual(self.pedir(c, recurso=99).status_code, 400)
        self.assertEqual(self.pedir(c, modulo=9).status_code, 400)
        self.assertEqual(self.pedir(c, fecha="2000-01-01").status_code, 400)

    def test_03_confirmar_y_rechazar(self):
        ana, lucia = self.cliente("ana", "ana123"), self.cliente("lucia", "lucia123")
        s1 = self.pedir(ana).get_json()["id"]
        s2 = self.pedir(ana, modulo=2).get_json()["id"]
        self.assertEqual(lucia.post(f"/api/solicitudes/{s1}/confirmar").get_json()["estado"], "CONFIRMADA")
        self.assertEqual(lucia.post(f"/api/solicitudes/{s2}/rechazar").get_json()["estado"], "RECHAZADA")

    def test_04_no_duplica_confirmada(self):
        ana, marcos = self.cliente("ana", "ana123"), self.cliente("marcos", "marcos123")
        lucia = self.cliente("lucia", "lucia123")
        s1 = self.pedir(ana).get_json()["id"]
        s2 = self.pedir(marcos).get_json()["id"]
        self.assertEqual(lucia.post(f"/api/solicitudes/{s1}/confirmar").status_code, 200)
        r = lucia.post(f"/api/solicitudes/{s2}/confirmar")
        self.assertEqual(r.status_code, 409)
        estado = marcos.get("/api/solicitudes").get_json()[0]["estado"]
        self.assertEqual(estado, "PENDIENTE")

    def test_05_docente_no_puede_confirmar(self):
        ana = self.cliente("ana", "ana123")
        s = self.pedir(ana).get_json()["id"]
        self.assertEqual(ana.post(f"/api/solicitudes/{s}/confirmar").status_code, 403)

    def test_06_sin_sesion(self):
        self.assertEqual(miapp.app.test_client().get("/api/solicitudes").status_code, 401)

    def test_07_docente_no_ve_ajenas(self):
        ana, marcos = self.cliente("ana", "ana123"), self.cliente("marcos", "marcos123")
        s = self.pedir(ana).get_json()["id"]
        self.assertEqual(marcos.get("/api/solicitudes").get_json(), [])
        self.assertEqual(marcos.get(f"/api/solicitudes/{s}/historial").status_code, 404)

    def test_08_no_se_resuelve_dos_veces(self):
        ana, lucia = self.cliente("ana", "ana123"), self.cliente("lucia", "lucia123")
        s = self.pedir(ana).get_json()["id"]
        lucia.post(f"/api/solicitudes/{s}/rechazar")
        self.assertEqual(lucia.post(f"/api/solicitudes/{s}/confirmar").status_code, 409)

    def test_09_reservas_por_recurso_y_fecha(self):
        ana, lucia = self.cliente("ana", "ana123"), self.cliente("lucia", "lucia123")
        s = self.pedir(ana).get_json()["id"]
        lucia.post(f"/api/solicitudes/{s}/confirmar")
        r = ana.get(f"/api/reservas?recurso_id=1&fecha={FUTURA}").get_json()
        self.assertEqual(len(r), 1)
        self.assertEqual(ana.get(f"/api/reservas?recurso_id=2&fecha={FUTURA}").get_json(), [])

    def test_10_login_incorrecto(self):
        r = miapp.app.test_client().post("/api/login", json={"usuario": "ana", "clave": "mala"})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
