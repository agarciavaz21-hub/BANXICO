import os
import sys
import time
import smtplib
import requests
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Carga las variables de entorno definidas en el archivo .env
load_dotenv()

TOKEN_BANXICO = os.getenv("Token")
HOST_SMTP = os.getenv("SMTP_SERVER", "smtp.gmail.com")
PUERTO_SMTP = int(os.getenv("SMTP_PORT", 587))
CORREO_REMITENTE = os.getenv("SMTP_USER")
CLAVE_CORREO = os.getenv("SMTP_PASSWORD")

URL_BANXICO = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{}/datos/oportuno"
SERIE_CETES_28 = "SF43936"
TASA_RESPALDO = 0.06  # Tasa de referencia en caso de que Banxico no responda


def pedir_que_sigue() -> None:
    """Consulta si el usuario desea regresar al menú o cerrar el programa."""
    print("\n==========================================")
    print("Seleccione la siguiente acción:")
    print("  [1] Regresar al menú principal")
    print("  [2] Finalizar el programa")
    print("==========================================")

    respuesta = input("Ingrese la opción deseada (1 o 2): ").strip()
    if respuesta == "2":
        apagar_programa()
    # Con "1" (o enter) se regresa al menú principal


def pedir_a_banxico(clave: str):
    """Realiza la petición GET a Banxico para la serie indicada."""
    cabeceras = {"Bmx-Token": TOKEN_BANXICO}
    return requests.get(URL_BANXICO.format(clave), headers=cabeceras, timeout=10)


def consultar_serie() -> None:
    """Solicita una clave de serie y muestra su dato más reciente."""
    if not TOKEN_BANXICO:
        print("\n[!] Error: no se localizó el Token en el archivo .env.")
        pedir_que_sigue()
        return

    clave = input("\nIngrese la clave de la serie de Banxico (ej. SF61745, SP68257): ").strip()

    if not clave:
        print("[!] Error: es necesario ingresar una clave de serie.")
        pedir_que_sigue()
        return

    try:
        print(f"\nConsultando la serie '{clave}' en Banxico...")
        respuesta = pedir_a_banxico(clave)

        if respuesta.status_code != 200:
            print(f"\n[!] Error de conexión o serie inexistente. Código HTTP: {respuesta.status_code}")
        else:
            contenido = respuesta.json()
            print("\nLa conexión con Banxico se realizó correctamente.")

            lista = contenido.get("bmx", {}).get("series", [])
            if not lista:
                print("Respuesta obtenida:", contenido)
            else:
                serie_info = lista[0]
                nombre = serie_info.get("titulo", "Sin título")
                registros = serie_info.get("datos", [])

                print("\n==========================================")
                print(f"Clave   -> {clave}")
                print(f"Nombre  -> {nombre}")
                if registros:
                    print(f"Fecha   -> {registros[0].get('fecha')}")
                    print(f"Valor   -> {registros[0].get('dato')}")
                else:
                    print("[!] La serie consultada no contiene observaciones.")
                print("==========================================")

    except requests.exceptions.RequestException as err:
        print(f"\n[!] No fue posible establecer conexión con Banxico: {err}")

    pedir_que_sigue()


def mandar_correo(para: str, titulo: str, mensaje: str) -> bool:
    """Envía un correo de texto plano con la configuración SMTP del .env."""
    if not CORREO_REMITENTE or not CLAVE_CORREO:
        print("\n[!] Error: faltan las credenciales SMTP_USER o SMTP_PASSWORD en el archivo .env.")
        return False

    try:
        correo = MIMEMultipart()
        correo["From"] = CORREO_REMITENTE
        correo["To"] = para
        correo["Subject"] = titulo
        correo.attach(MIMEText(mensaje, "plain"))

        print("\nEstableciendo conexión con el servidor de correo...")
        conexion = smtplib.SMTP(HOST_SMTP, PUERTO_SMTP)
        conexion.starttls()
        conexion.login(CORREO_REMITENTE, CLAVE_CORREO)

        conexion.send_message(correo)
        conexion.quit()
        print("El correo fue enviado exitosamente.")
        return True

    except Exception as err:
        print(f"[!] No fue posible enviar el correo: {err}")
        return False


def obtener_tasa_cetes() -> float:
    """Regresa la tasa anual de CETES (en decimal) o la de respaldo si falla."""
    try:
        print("\nObteniendo la tasa semanal vigente de CETES desde Banxico...")
        respuesta = pedir_a_banxico(SERIE_CETES_28)

        if respuesta.status_code == 200:
            lista = respuesta.json().get("bmx", {}).get("series", [])
            if lista:
                registros = lista[0].get("datos", [])
                if registros:
                    texto_tasa = registros[0].get("dato")
                    tasa = float(texto_tasa) / 100
                    print(f"[+] Tasa de CETES al {registros[0].get('fecha')}: {texto_tasa}% anual")
                    return tasa
        else:
            print(f"[!] Banxico no respondió correctamente (Código {respuesta.status_code}). Se utilizará la tasa de referencia de 6.0%.")
    except Exception as err:
        print(f"[!] Error al consultar la tasa de CETES: {err}. Se utilizará la tasa de referencia de 6.0%.")

    return TASA_RESPALDO


def simular_cetes() -> None:
    """
    Obtiene la tasa de CETES, solicita monto y plazo, calcula el interés
    y envía el reporte por correo electrónico.
    """
    if not TOKEN_BANXICO:
        print("\n[!] Error: no se localizó el Token en el archivo .env.")
        pedir_que_sigue()
        return

    tasa = obtener_tasa_cetes()

    try:
        print("\n--- Simulador de Interés CETES (ISC) ---")
        capital = float(input("Ingrese el monto a invertir ($): "))

        print("\nReferencias de plazo:")
        print("   3 meses  = 13 semanas")
        print("   6 meses  = 26 semanas")
        print("  12 meses  = 52 semanas")
        num_semanas = int(input("Ingrese el plazo de la inversión en semanas: "))

        if capital <= 0 or num_semanas <= 0:
            print("[!] Error: el monto y el plazo deben ser mayores a cero.")
            pedir_que_sigue()
            return

        # Conversión de semanas a días con año comercial de 360 días
        num_dias = num_semanas * 7
        ganancia = capital * tasa * (num_dias / 360)
        total = capital + ganancia

        texto_reporte = (
            f"********** Reporte ISC (CETES) **********\n"
            f"Tasa CETES usada    : {tasa * 100:.2f}% anual\n"
            f"Capital invertido   : ${capital:,.2f}\n"
            f"Plazo               : {num_semanas} semana(s) ({num_dias} días)\n"
            f"Interés generado    : ${ganancia:,.2f}\n"
            f"-----------------------------------------\n"
            f"Total final         : ${total:,.2f}\n"
            f"*****************************************"
        )
        # El reporte debe llegar únicamente por correo; para verlo en terminal: print(f"\n{texto_reporte}")

        destino = input("\nIngrese el correo electrónico para recibir el reporte: ").strip()

        print("\nGenerando el reporte...")
        time.sleep(2)

        if destino:
            mandar_correo(
                para=destino,
                titulo="Reporte. Cálculo de Interés CETES (ISC)",
                mensaje=texto_reporte
            )

    except ValueError:
        print("\n[!] Error: ingrese únicamente valores numéricos válidos.")
    except Exception as err:
        print(f"[!] Error durante el cálculo: {err}")

    pedir_que_sigue()


def apagar_programa() -> None:
    """Cierra el programa con una breve cuenta regresiva de puntos."""
    print("\nFinalizando el programa...")
    for puntos in ("...", "..", "."):
        time.sleep(0.75)
        print(puntos)
    time.sleep(0.75)
    print("Programa finalizado.")
    sys.exit()


def menu_principal() -> None:
    """Muestra el menú en ciclo y ejecuta la opción seleccionada."""
    acciones = {
        "1": consultar_serie,
        "2": simular_cetes,
        "3": apagar_programa,
    }

    while True:
        print("\n##########################################")
        print("             MENÚ PRINCIPAL               ")
        print("##########################################")
        print("1. Consultar una serie de Banxico")
        print("2. Calcular interés con CETES")
        print("3. Cerrar el programa")
        print("##########################################")

        try:
            eleccion = input("Seleccione una opción: ").strip()
            accion = acciones.get(eleccion)

            if accion:
                accion()
            else:
                print("\n[!] Opción no válida. Ingrese 1, 2 o 3.")

        except KeyboardInterrupt:
            print("\n\n[!] Se detectó una interrupción del sistema.")
            apagar_programa()
        except Exception as err:
            print(f"\n[!] Error inesperado: {err}")


if __name__ == "__main__":
    menu_principal()