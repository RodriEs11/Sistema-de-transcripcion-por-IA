// Puente con la página del Servidor: lo que la página le pide a la app (MensajeDeLaPantalla) y lo que la app
// le avisa a la página (AnunciarApp, EjecutarEnWeb; otras llamadas en Autocorreccion y Configuracion).
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
        // La pantalla del Servidor avisa: {accion:"agrandar"} | {accion:"compacto"} | {accion:"tema", oscuro:true}
        // | {accion:"configuracion"} (pide el estado) | {accion:"cfg", que, valor} (cambio en Configuración)
        void MensajeDeLaPantalla(CoreWebView2WebMessageReceivedEventArgs e)
        {
            try
            {
                if (string.IsNullOrEmpty(Config.Url) || !e.Source.StartsWith(Config.Url, StringComparison.OrdinalIgnoreCase)) return;
                var d = Config.Json.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
                object v;
                string accion = d != null && d.TryGetValue("accion", out v) ? v + "" : "";
                if (accion == "agrandar") SalirCompacto();
                else if (accion == "compacto") EntrarCompacto();
                else if (accion == "autocorreccion") EnviarAutocorreccion(false);
                else if (accion == "audio") AudioDeLaPantalla(d);
                else if (accion == "configuracion") EnviarEstadoConfig();
                else if (accion == "cfg") CambioDeConfig(d.TryGetValue("que", out v) ? v + "" : "", d.TryGetValue("valor", out v) ? v : null);
                else if (accion == "tema")
                {
                    bool oscuro = d.TryGetValue("oscuro", out v) && v is bool && (bool)v;
                    if (oscuro != Config.Oscuro) { Config.Oscuro = oscuro; GuardarConfig(); }
                    AplicarTema(oscuro);
                }
            }
            catch (Exception ex) { Registro.Escribir("Mensaje de la pantalla ilegible: " + ex.Message); }
        }

        void AnunciarApp()
        {
            try
            {
                if (web.CoreWebView2 != null)
                    web.CoreWebView2.ExecuteScriptAsync("window.ponerApp && ponerApp({version:'" + Programa.VERSION + "', cola:true})").ContinueWith(t => { });
            }
            catch (Exception ex) { Registro.Escribir("No pude avisar a la pantalla la versión: " + ex.Message); }
        }

        void EjecutarEnWeb(string js)
        {
            try
            {
                if (web.CoreWebView2 != null)
                    web.CoreWebView2.ExecuteScriptAsync("window.ponerCompacto && " + js).ContinueWith(t => { });
            }
            catch (Exception ex) { Registro.Escribir("No pude avisar a la pantalla: " + ex.Message); }
        }
    }
}
