// Audios cargados desde la pantalla: van a la cola cifrada de la app.
// Parte de la clase VentanaPrincipal (partial): los campos y el constructor están en VentanaPrincipal.cs.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Transcripcion
{
    partial class VentanaPrincipal
    {
        // ------------------------------------------------------------ audios cargados desde la pantalla (1.6)
        // La pantalla le pasa a la app los audios que se arrastran o se eligen con "Cargar audio": van a la misma
        // cola cifrada que los del sistema, así que funcionan aunque no haya conexión con el Servidor (se envían
        // solos cuando vuelve). Así la pantalla no depende de que el Servidor responda para recibir un audio.
        string TituloAudioCargado()
        {
            return estado == Conexion.SinConexion || estado == Conexion.Buscando
                ? "Audio guardado en esta PC · se envía solo cuando vuelva la conexión"
                : "Audio cargado · enviando al Servidor";
        }

        void AudioDeLaPantalla(Dictionary<string, object> d)
        {
            object v;
            string id = d.TryGetValue("id", out v) ? v + "" : "";
            string nombre = Path.GetFileName(d.TryGetValue("nombre", out v) ? v + "" : "");
            string ok = "false", msg;
            try
            {
                if (nombre == "") nombre = "audio.wav";
                byte[] datos = Convert.FromBase64String(d.TryGetValue("datos", out v) ? v + "" : "");
                if (datos.Length == 0) throw new Exception("el archivo está vacío");
                cola.Agregar(nombre, datos, Vigilante.Huella(datos));
                Registro.Escribir("Cargado desde la pantalla: " + nombre + " (" + datos.Length / 1024 + " KB)");
                MostrarAviso(TituloAudioCargado(), nombre);
                ok = "true";
                msg = estado == Conexion.SinConexion || estado == Conexion.Buscando ? "guardado" : "enviando";
            }
            catch (Exception ex)
            {
                Registro.Escribir("No pude cargar " + nombre + " desde la pantalla: " + ex.Message);
                msg = ex.Message;
            }
            EjecutarEnWeb("window.audioEnCola && audioEnCola(" + Config.Json.Serialize(id) + ", " + ok + ", " + Config.Json.Serialize(msg) + ")");
        }
    }
}
