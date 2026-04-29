"""
app.py — Interfaz Web del Sistema de Control de Presencia
=========================================================
Cliente Streamlit que consume la API REST del backend.
Gestiona autenticación, fichaje, historial, informes y administración.
"""

import os
import json
import io
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
from streamlit_js_eval import get_geolocation, streamlit_js_eval


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Control de Presencia", page_icon="🕒", layout="wide")

API        = os.getenv("API_URL", "http://backend:8000")
API_PUBL   = os.getenv("API_URL_PUBLICA", "http://localhost:8000")
TIMEOUT    = 10
SESSION_H  = 8  # Horas de validez de la sesión en el navegador


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE API
# ─────────────────────────────────────────────────────────────────────────────

def headers():
    """Cabeceras HTTP con el token JWT de la sesión activa."""
    return {"Authorization": f"Bearer {st.session_state.get('token', '')}"}


def api(method: str, path: str, **kwargs) -> requests.Response | None:
    """
    Realiza una petición HTTP autenticada al backend.
    Devuelve None y muestra un error si la conexión falla.
    """
    try:
        fn = getattr(requests, method)
        return fn(f"{API}{path}", headers=headers(), timeout=TIMEOUT, **kwargs)
    except requests.exceptions.ConnectionError:
        st.error("❌ No se puede conectar con el servidor. Comprueba que los servicios están activos.")
        return None
    except requests.exceptions.Timeout:
        st.error("❌ El servidor tardó demasiado en responder.")
        return None


def get(path):   return api("get", path)
def post(path, **kw): return api("post", path, **kw)
def put(path, **kw):  return api("put", path, **kw)


def ok(resp, success_msg=None) -> bool:
    """Comprueba la respuesta, muestra mensaje o error. Devuelve True si fue exitosa."""
    if resp is None:
        return False
    if resp.status_code in (200, 201):
        if success_msg:
            st.success(success_msg)
        return True
    try:
        detalle = resp.json().get("detail", "Error desconocido.")
    except Exception:
        detalle = "Error del servidor."
    st.error(f"❌ {detalle}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# SESIÓN
# ─────────────────────────────────────────────────────────────────────────────

def init():
    """Inicializa las variables de estado de Streamlit."""
    defaults = {"logged_in": False, "user": {}, "token": "", "seccion": "Fichar"}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def recuperar_sesion():
    """Intenta recuperar la sesión almacenada en localStorage del navegador."""
    if st.session_state.logged_in:
        return
    try:
        raw = streamlit_js_eval(js_expressions="localStorage.getItem('sess')", key="get_sess")
        if not raw:
            return
        data   = json.loads(raw)
        expiry = datetime.fromisoformat(data["expiry"])
        if datetime.now() < expiry:
            st.session_state.logged_in = True
            st.session_state.user      = data["user"]
            st.session_state.token     = data["token"]
        else:
            streamlit_js_eval(js_expressions="localStorage.removeItem('sess')", key="rm_sess")
    except Exception:
        pass


def guardar_sesion(user: dict, token: str):
    """Persiste la sesión en localStorage con fecha de expiración."""
    expiry = datetime.now() + timedelta(hours=SESSION_H)
    data   = json.dumps({"user": user, "token": token, "expiry": expiry.isoformat()})
    streamlit_js_eval(js_expressions=f"localStorage.setItem('sess', `{data}`)", key="set_sess")


def logout():
    """Cierra la sesión y limpia el localStorage."""
    streamlit_js_eval(js_expressions="localStorage.removeItem('sess')", key="rm_sess_out")
    for k in ("logged_in", "user", "token"):
        st.session_state[k] = False if k == "logged_in" else ""
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA DE LOGIN
# ─────────────────────────────────────────────────────────────────────────────

def pantalla_login():
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 🕒 Control de Presencia")
        st.markdown("---")

        with st.form("login"):
            email    = st.text_input("📧 Email corporativo")
            password = st.text_input("🔒 Contraseña", type="password")
            submit   = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if submit:
            if not email or not password:
                st.warning("Introduce el email y la contraseña.")
                return
            try:
                resp = requests.post(f"{API}/auth/login",
                                     json={"email": email, "password": password}, timeout=TIMEOUT)
            except Exception:
                st.error("No se puede conectar con el servidor.")
                return

            if resp.status_code == 200:
                data = resp.json()
                user = {"id": data["user_id"], "nombre": data["nombre"], "rol": data["rol"]}
                st.session_state.logged_in = True
                st.session_state.user      = user
                st.session_state.token     = data["access_token"]
                guardar_sesion(user, data["access_token"])
                st.rerun()
            elif resp.status_code == 429:
                st.error(resp.json().get("detail", "Cuenta bloqueada temporalmente."))
            else:
                st.error("Email o contraseña incorrectos.")


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def sidebar(user: dict):
    with st.sidebar:
        st.markdown(f"### 👤 {user['nombre']}")
        st.caption(f"Rol: {user['rol'].capitalize()}")
        st.divider()

        secciones = ["🚀 Fichar", "📊 Historial", "📈 Informes"]
        if user["rol"] == "admin":
            secciones += ["👥 Empleados", "⚠️ Alertas", "📂 Documentos y Preavisos", "🔍 Logs"]

        for s in secciones:
            label = s.split(" ", 1)[1]  # Etiqueta sin emoji para comparar
            if st.button(s, use_container_width=True):
                st.session_state.seccion = label

        st.divider()
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            logout()


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: FICHAR
# ─────────────────────────────────────────────────────────────────────────────

def seccion_fichar(user: dict):
    st.title("🚀 Registrar Fichaje")

    # ── Notificaciones de preavisos ───────────────────────────────────────────
    r = get("/preavisos/mis_preavisos")
    if r and r.status_code == 200:
        notifs = [p for p in r.json() if p["estado"] != "pendiente" and not p["visto_usuario"]]
        if notifs:
            with st.expander("🔔 Notificaciones pendientes", expanded=True):
                for p in notifs:
                    fecha = datetime.strptime(p["fecha_ausencia"], "%Y-%m-%d").strftime("%d/%m/%Y")
                    msg   = f"Tu solicitud de **{p['tipo'].capitalize()}** para el {fecha} fue **{p['estado']}**."
                    (st.success if p["estado"] == "aceptado" else st.error)(msg)
                    if st.button("Marcar leído", key=f"leido_{p['id']}"):
                        post(f"/preavisos/{p['id']}/marcar_visto")
                        st.rerun()

    # ── Documentos asignados ──────────────────────────────────────────────────
    r = get("/documentos/mis_documentos")
    if r and r.status_code == 200 and r.json():
        st.subheader("📄 Documentos recibidos")
        for d in r.json():
            icono = "✅" if d["leido"] else "🆕"
            st.markdown(f"{icono} [{d['titulo']}]({API_PUBL}/documentos/{d['id']}/descargar)")

    st.divider()

    # ── Geolocalización GPS ───────────────────────────────────────────────────
    st.subheader("📍 Ubicación GPS")
    loc = get_geolocation()

    if loc and "coords" in loc:
        lat = round(loc["coords"].get("latitude",  0.0), 6)
        lon = round(loc["coords"].get("longitude", 0.0), 6)
        acc = loc["coords"].get("accuracy", 0)
        st.success(f"Posición detectada: **{lat}, {lon}** (precisión: ±{acc:.0f} m)")
    else:
        lat, lon = 0.0, 0.0
        st.warning("No se pudo obtener la ubicación GPS. El fichaje se registrará sin coordenadas.")

    # ── Botones de fichaje ────────────────────────────────────────────────────
    st.subheader("⏱️ Tipo de fichaje")
    col1, col2, col3, col4 = st.columns(4)
    tipos = [("entrada", "🟢 Entrada", col1), ("descanso", "☕ Descanso", col2),
             ("comida",  "🍽️ Comida",  col3), ("salida",   "🔴 Salida",  col4)]

    for tipo, label, col in tipos:
        if col.button(label, use_container_width=True):
            r = post("/fichajes/", json={"tipo": tipo, "lat": lat, "lon": lon})
            if r and r.status_code == 200:
                zona = "dentro de la zona ✅" if r.json()["dentro_zona"] else "fuera de zona ⚠️"
                st.success(f"Fichaje de **{label}** registrado correctamente ({zona}).")
            elif r and r.status_code == 409:
                st.error(r.json().get("detail"))
            elif r:
                st.error("Error al registrar el fichaje.")

    st.divider()

    # ── Formulario de preaviso ────────────────────────────────────────────────
    st.subheader("📝 Solicitar ausencia o retraso")
    with st.form("preaviso", clear_on_submit=True):
        c1, c2 = st.columns(2)
        tipo_prev  = c1.selectbox("Tipo", ["Falta", "Retraso"])
        fecha_prev = c2.date_input("Fecha", min_value=date.today() + timedelta(days=1))
        motivo     = st.text_area("Motivo *", placeholder="Mínimo 5 caracteres...")
        enviado    = st.form_submit_button("Enviar solicitud", type="primary")

    if enviado:
        r = post("/preavisos/", json={"tipo": tipo_prev.lower(), "fecha": str(fecha_prev), "motivo": motivo})
        ok(r, "Solicitud enviada correctamente. El administrador la revisará en breve.")


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: HISTORIAL
# ─────────────────────────────────────────────────────────────────────────────

def seccion_historial():
    st.title("📊 Historial de Fichajes")

    r = get("/fichajes/mis_fichajes")
    if not r or r.status_code != 200:
        st.error("No se pudo cargar el historial.")
        return

    datos = r.json()
    if not datos:
        st.info("Aún no tienes fichajes registrados.")
        return

    df = pd.DataFrame(datos)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # ── Filtro por fechas ─────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    desde = c1.date_input("Desde", value=date.today() - timedelta(days=30))
    hasta = c2.date_input("Hasta", value=date.today())

    mask = (df["timestamp"].dt.date >= desde) & (df["timestamp"].dt.date <= hasta)
    df_f = df[mask].copy()

    if df_f.empty:
        st.info("No hay fichajes en el rango de fechas seleccionado.")
        return

    # ── Exportar CSV ──────────────────────────────────────────────────────────
    r_csv = get("/fichajes/exportar_csv")
    if r_csv and r_csv.status_code == 200:
        st.download_button("📥 Descargar CSV completo", r_csv.content, "fichajes.csv", "text/csv")

    # ── Tabla ─────────────────────────────────────────────────────────────────
    df_show = df_f.copy()
    df_show["Fecha"] = df_show["timestamp"].dt.strftime("%d/%m/%Y")
    df_show["Hora"]  = df_show["timestamp"].dt.strftime("%H:%M:%S")
    df_show["Tipo"]  = df_show["tipo"].str.capitalize()
    df_show["Zona"]  = df_show["dentro_zona"].map({True: "✅ Sí", False: "⚠️ No"})
    st.dataframe(df_show[["Fecha", "Hora", "Tipo", "Zona"]], use_container_width=True)

    # ── Mapa ──────────────────────────────────────────────────────────────────
    mapa = df_f[["latitud", "longitud"]].rename(columns={"latitud": "lat", "longitud": "lon"})
    mapa = mapa[(mapa["lat"] != 0) & (mapa["lon"] != 0)].dropna()
    if not mapa.empty:
        st.subheader("🗺️ Mapa de fichajes")
        st.map(mapa)


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: INFORMES
# ─────────────────────────────────────────────────────────────────────────────

def seccion_informes():
    st.title("📈 Informes")

    c1, c2 = st.columns(2)
    anio = c1.number_input("Año", min_value=2020, max_value=2030, value=date.today().year)
    mes  = c2.selectbox("Mes", range(1, 13), index=date.today().month - 1,
                        format_func=lambda m: date(2000, m, 1).strftime("%B").capitalize())

    tab_mensual, tab_diario = st.tabs(["📅 Resumen mensual", "📋 Detalle por día"])

    with tab_mensual:
        r = get(f"/fichajes/resumen_mensual?anio={anio}&mes={mes}")
        if r and r.status_code == 200:
            data = r.json()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Días trabajados",   data["total_dias"])
            col2.metric("Horas totales",      f"{data['total_horas']:.1f} h")
            col3.metric("Días laborables",    data["dias_laborables"])
            col4.metric("Faltas",             data["dias_falta"],
                        delta=f"-{data['dias_falta']}" if data["dias_falta"] else None,
                        delta_color="inverse")

    with tab_diario:
        fecha = st.date_input("Seleccionar día", value=date.today())
        r = get(f"/fichajes/resumen_diario?fecha={fecha}")
        if r and r.status_code == 200:
            data = r.json()
            st.metric("Horas trabajadas", f"{data['horas_trabajadas']:.2f} h")
            if data["fichajes"]:
                df = pd.DataFrame(data["fichajes"])
                df.columns = ["Tipo", "Hora", "Latitud", "Longitud", "En zona"]
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Sin fichajes para esta fecha.")


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN ADMIN: EMPLEADOS
# ─────────────────────────────────────────────────────────────────────────────

def seccion_empleados():
    st.title("👥 Gestión de Empleados")
    tab_monitor, tab_alta, tab_lista = st.tabs(["🕵️ Monitor", "➕ Alta", "📋 Lista"])

    with tab_monitor:
        st.subheader("Estado en tiempo real")
        if st.button("🔄 Actualizar"):
            st.rerun()
        r = get("/fichajes/estado_empleados")
        if r and r.status_code == 200:
            for emp in r.json():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.write(f"**{emp['nombre']}** — {emp['email']}")
                    estado = emp["ultimo_evento"]
                    if estado == "entrada":
                        c2.success("🟢 Trabajando")
                    elif estado in ("comida", "descanso"):
                        c2.warning("🟡 En pausa")
                    elif estado == "salida":
                        c2.error("🔴 Fuera")
                    else:
                        c2.info("⚪ Sin registro")
                    c3.write(f"🕒 {emp['hora']}")

    with tab_alta:
        st.subheader("Registrar nuevo empleado")
        with st.form("alta_usuario", clear_on_submit=True):
            nombre   = st.text_input("Nombre completo *")
            email    = st.text_input("Email corporativo *")
            password = st.text_input("Contraseña provisional *", type="password")
            rol      = st.selectbox("Rol", ["user", "admin"])
            submit   = st.form_submit_button("Registrar", type="primary")
        if submit:
            r = post("/usuarios/", json={"nombre": nombre, "email": email,
                                         "password": password, "rol": rol})
            ok(r, f"Usuario **{nombre}** registrado correctamente.")

    with tab_lista:
        st.subheader("Empleados registrados")
        r = get("/usuarios/")
        if r and r.status_code == 200:
            usuarios = r.json()
            for u in usuarios:
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                    c1.write(f"**{u['nombre']}** — {u['email']}")
                    c2.write(f"Rol: {u['rol']}")
                    estado = "✅ Activo" if u["activo"] else "❌ Inactivo"
                    c3.write(estado)
                    if u["activo"]:
                        if c4.button("Desactivar", key=f"des_{u['id']}"):
                            r2 = put(f"/usuarios/{u['id']}/desactivar")
                            ok(r2, "Usuario desactivado.")
                            st.rerun()
                    else:
                        if c4.button("Activar", key=f"act_{u['id']}"):
                            r2 = put(f"/usuarios/{u['id']}/activar")
                            ok(r2, "Usuario activado.")
                            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN ADMIN: ALERTAS
# ─────────────────────────────────────────────────────────────────────────────

def seccion_alertas():
    st.title("⚠️ Alertas del Sistema")

    if st.button("🔄 Generar alertas de hoy"):
        r = get("/alertas/generar")
        if r and r.status_code == 200:
            data = r.json()
            if "nuevas_alertas" in data:
                st.success(f"Generadas {data['nuevas_alertas']} alertas nuevas.")
            else:
                st.info(data.get("mensaje", "Sin alertas nuevas."))

    r = get("/usuarios/")
    if not r or r.status_code != 200:
        return

    empleados = {f"{u['nombre']} ({u['email']})": u["id"]
                 for u in r.json() if u["rol"] == "user"}

    seleccionado = st.selectbox("Seleccionar empleado:", ["— Todos —"] + list(empleados.keys()))
    if seleccionado != "— Todos —":
        uid = empleados[seleccionado]
        r2  = get(f"/alertas/admin/{uid}")
        if r2 and r2.status_code == 200:
            alertas = r2.json()
            if alertas:
                df = pd.DataFrame(alertas)[["fecha", "motivo"]]
                df.columns = ["Fecha", "Motivo"]
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Sin alertas para este empleado.")


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN ADMIN: DOCUMENTOS Y PREAVISOS
# ─────────────────────────────────────────────────────────────────────────────

def seccion_documentos_preavisos():
    st.title("📂 Documentos y Preavisos")
    tab_docs, tab_prev = st.tabs(["📤 Documentos", "📬 Preavisos"])

    with tab_docs:
        r = get("/usuarios/")
        destinatarios = {}
        if r and r.status_code == 200:
            destinatarios = {f"{u['nombre']} ({u['email']})": u["id"]
                             for u in r.json() if u["rol"] == "user"}

        with st.expander("Enviar documento", expanded=True):
            with st.form("enviar_doc", clear_on_submit=True):
                dest    = st.selectbox("Destinatario *", list(destinatarios.keys()) or ["Sin empleados"])
                titulo  = st.text_input("Título *")
                archivo = st.file_uploader("Archivo *", type=["pdf", "docx", "jpg", "png"])
                submit  = st.form_submit_button("Enviar", type="primary")
            if submit and archivo and titulo and destinatarios:
                uid = destinatarios[dest]
                r2  = post("/documentos/",
                           data={"usuario_id": uid, "titulo": titulo},
                           files={"archivo": (archivo.name, archivo.getvalue())})
                ok(r2, "Documento enviado correctamente.")

        st.subheader("Estado de lectura")
        r = get("/documentos/admin/todos")
        if r and r.status_code == 200 and r.json():
            filas = [{"Empleado": d["usuario_nombre"], "Documento": d["titulo"],
                      "Leído": "✅" if d["leido"] else "❌", "Enviado": d["fecha_envio"][:10]}
                     for d in r.json()]
            st.dataframe(pd.DataFrame(filas), use_container_width=True)

    with tab_prev:
        r = get("/admin/preavisos/")
        if not r or r.status_code != 200:
            st.error("No se pudieron cargar los preavisos.")
            return

        todos = r.json()
        pendientes = [p for p in todos if p["estado"] == "pendiente"]
        procesados = [p for p in todos if p["estado"] != "pendiente"]

        st.subheader(f"Pendientes ({len(pendientes)})")
        if not pendientes:
            st.info("No hay solicitudes pendientes.")
        for p in pendientes:
            with st.container(border=True):
                fecha = datetime.strptime(p["fecha_ausencia"], "%Y-%m-%d").strftime("%d/%m/%Y")
                st.write(f"**{p['usuario_nombre']}** — {p['tipo'].capitalize()} ({fecha})")
                st.caption(f"Motivo: {p['motivo']}")
                c1, c2, _ = st.columns([1, 1, 4])
                if c1.button("✅ Aceptar",  key=f"ac_{p['id']}"):
                    ok(post(f"/admin/preavisos/{p['id']}/decidir", json={"estado": "aceptado"}),
                       "Preaviso aceptado.")
                    st.rerun()
                if c2.button("❌ Rechazar", key=f"re_{p['id']}"):
                    ok(post(f"/admin/preavisos/{p['id']}/decidir", json={"estado": "rechazado"}),
                       "Preaviso rechazado.")
                    st.rerun()

        if procesados:
            st.subheader("Historial procesado")
            df = pd.DataFrame(procesados)
            df["fecha_ausencia"] = pd.to_datetime(df["fecha_ausencia"]).dt.strftime("%d/%m/%Y")
            st.dataframe(df[["usuario_nombre", "tipo", "fecha_ausencia", "motivo", "estado"]]
                         .rename(columns={"usuario_nombre": "Empleado", "tipo": "Tipo",
                                          "fecha_ausencia": "Fecha", "motivo": "Motivo",
                                          "estado": "Resolución"}),
                         use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN ADMIN: LOGS
# ─────────────────────────────────────────────────────────────────────────────

def seccion_logs():
    st.title("🔍 Logs de Auditoría")
    st.info("Los logs del sistema se guardan en el archivo `logs/fichaje.log` dentro del contenedor del backend. "
            "Puedes consultarlos con: `docker exec asir_backend tail -100 /app/logs/fichaje.log`")

    st.subheader("Últimas líneas del log (via Docker)")
    st.code("docker exec asir_backend tail -50 /app/logs/fichaje.log", language="bash")
    st.code("docker-compose logs backend --tail=100", language="bash")


# ─────────────────────────────────────────────────────────────────────────────
# ENRUTADOR PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

SECCIONES = {
    "Fichar":              seccion_fichar,
    "Historial":           seccion_historial,
    "Informes":            seccion_informes,
    "Empleados":           seccion_empleados,
    "Alertas":             seccion_alertas,
    "Documentos y Preavisos": seccion_documentos_preavisos,
    "Logs":                seccion_logs,
}

SOLO_ADMIN = {"Empleados", "Alertas", "Documentos y Preavisos", "Logs"}


def main():
    init()
    recuperar_sesion()

    if not st.session_state.logged_in:
        pantalla_login()
        st.stop()

    user    = st.session_state.user
    seccion = st.session_state.get("seccion", "Fichar")

    sidebar(user)

    # Protección adicional: evitar acceso directo a secciones de admin.
    if seccion in SOLO_ADMIN and user["rol"] != "admin":
        st.error("No tienes permiso para acceder a esta sección.")
        st.stop()

    fn = SECCIONES.get(seccion, seccion_fichar)
    # La función de fichaje recibe el usuario; el resto no.
    if seccion == "Fichar":
        fn(user)
    else:
        fn()


main()
