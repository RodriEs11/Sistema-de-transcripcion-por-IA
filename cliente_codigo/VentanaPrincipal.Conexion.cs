// Conexión con el Servidor: consulta de estado cada 10 s y aviso de casos listos para revisar.
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
        // ------------------------------------------------------------ conexión
        Task ConsultarEstado() { return ConsultarEstado(false); }

        // forzar: probar ya aunque haya otra consulta esperando respuesta (p. ej. de la dirección anterior)
        async Task ConsultarEstado(bool forzar)
        {
            if (consultando > 0 && !forzar) return;
            consultando++;
            try
            {
                string probada = Config.Url;
                Respuesta r = string.IsNullOrEmpty(probada) ? null : await Servidor.Estado(probada);
                if (probada != Config.Url) return;      // la dirección se cambió a mano mientras tanto
                if (r != null && r.Codigo == 401) { PedirVincularDeNuevo(); return; }
                if (r == null || !r.Ok)
                {   // ¿cambió la dirección del túnel? (el Servidor se reinició)
                    if (estado != Conexion.SinConexion) PonerEstado(Conexion.Buscando, null);
                    string nueva = await Servidor.BuscarDireccion();
                    if (probada != Config.Url) return;
                    if (nueva != null && nueva != Config.Url)
                    {
                        var r2 = await Servidor.Estado(nueva);
                        if (probada != Config.Url) return;
                        if (r2.Ok)
                        {
                            Registro.Escribir("Nueva dirección del Servidor: " + nueva);
                            Config.Url = nueva; Config.Guardar(); r = r2;
                        }
                    }
                }
                if (r != null && r.Ok)
                {
                    bool ia = r.Datos.ContainsKey("ia") && r.Datos["ia"] is bool && (bool)r.Datos["ia"];
                    PonerEstado(ia ? Conexion.Conectado : Conexion.IaNoLista, r);
                    RevisarListos(r);
                    cola.Despertar();
                    var app = r.Datos.ContainsKey("app") ? r.Datos["app"] as Dictionary<string, object> : null;
                    if (app != null && app.ContainsKey("huella"))
                    {   // ¿hay una versión nueva de esta aplicación en el Servidor? (se baja en segundo plano)
                        Actualizador.Revisar(Config.Url, app["huella"] + "", app.ContainsKey("version") ? app["version"] + "" : "").ContinueWith(_ => { });
                    }
                    Actualizador.EnviarAvisos(Config.Url).ContinueWith(_ => { });
                    if (urlCargada != Config.Url) await Entrar();
                }
                else
                {
                    PonerEstado(Conexion.SinConexion, null);
                    if (!webLista && !webFalla && !webCaida) cartel.Text = "No hay conexión con el Servidor.\nPuede estar apagado o sin internet en este momento.\nSe vuelve a intentar solo cada 10 segundos; no hace falta hacer nada.";
                }
            }
            catch (Exception ex) { Registro.Escribir("Error consultando estado: " + ex.Message); }
            finally { consultando--; }
        }

        // Notificación de Windows cuando un audio de esta PC queda listo para revisar.
        void RevisarListos(Respuesta r)
        {
            object o;
            if (!r.Datos.TryGetValue("casos", out o)) return;
            var lista = o as System.Collections.IEnumerable;
            if (lista == null || o is string) return;
            foreach (var x in lista)
            {
                var c = x as Dictionary<string, object>;
                if (c == null) continue;
                string nombre = c["nombre"] + "", est = c["estado"] + "";
                string titulo = c.ContainsKey("titulo") ? c["titulo"] + "" : nombre;
                string antes;
                estadosCasos.TryGetValue(nombre, out antes);
                estadosCasos[nombre] = est;
                if (!primeraLectura && est == "listo" && antes != "listo" && Config.AvisarListos)
                {
                    string marcas = c.ContainsKey("marcas") && c["marcas"] != null ? c["marcas"] + " marcas para revisar" : "Listo para revisar";
                    Notificaciones.Globo(bandeja, 8000, "Listo: " + titulo, marcas);
                    MostrarAviso("Listo para revisar: " + titulo, marcas);
                }
            }
            primeraLectura = false;
        }
    }
}
