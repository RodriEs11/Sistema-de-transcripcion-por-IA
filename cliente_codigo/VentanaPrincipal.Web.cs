// Interfaz web (WebView2): iniciar, cartel propio si la página no carga, reintentar, entrar con código, abrir en Edge.
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
        // ------------------------------------------------------------ interfaz web
        async Task IniciarWeb()
        {
            try
            {
                var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(Config.Carpeta, "WebView2"));
                await web.EnsureCoreWebView2Async(env);
            }
            catch (Exception ex)
            {
                webFalla = true;
                Registro.Escribir("WebView2 no disponible: " + ex.Message);
                cartel.Text = "Esta PC no tiene el componente de Edge que muestra la pantalla dentro de la aplicación.\n" +
                              "Los audios se siguen enviando igual. Para revisar, abrí la pantalla en Edge:";
                btnEdge.Visible = true;
                return;
            }
            var c = web.CoreWebView2;
            c.Settings.AreDevToolsEnabled = false;
            c.Settings.IsStatusBarEnabled = false;
            c.Settings.AreBrowserAcceleratorKeysEnabled = true;
            c.Settings.IsPasswordAutosaveEnabled = false;
            c.Settings.IsGeneralAutofillEnabled = false;
            // 1.12: sin la página de aviso de Microsoft Dev Tunnels (la pantalla del Servidor y todo lo que pide)
            try
            {
                c.AddWebResourceRequestedFilter("https://*.devtunnels.ms/*", CoreWebView2WebResourceContext.All);
                c.WebResourceRequested += (s, e) =>
                {
                    try { e.Request.Headers.SetHeader(Servidor.SaltarAviso, "true"); } catch { }
                };
            }
            catch (Exception ex) { Registro.Escribir("No se pudo preparar el encabezado de Dev Tunnels: " + ex.Message); }
            c.NavigationStarting += (s, e) =>
            {
                Uri u;
                if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out u) || u.Scheme == "data" || u.Scheme == "about") return;
                if (!string.IsNullOrEmpty(Config.Url) && !e.Uri.StartsWith(Config.Url, StringComparison.OrdinalIgnoreCase))
                {   // cualquier enlace de afuera se abre en el navegador
                    e.Cancel = true; Abrir(e.Uri); return;
                }
                if (u.AbsolutePath == "/entrar" && !u.Query.Contains("codigo="))
                {   // la sesión venció: entrar de nuevo con la llave de esta PC, sin pedir contraseña
                    e.Cancel = true; urlCargada = null;
                    BeginInvoke(new Action(async () => await Entrar()));
                    return;
                }
                navActual = e.Uri;
            };
            c.WebResourceResponseReceived += (s, e) =>
            {   // la respuesta de la página llega antes de que se dibuje: si es un error, se esconde ya
                try
                {
                    if (navActual == null || e.Request.Uri != navActual) return;
                    int cod = e.Response.StatusCode;
                    if (cod >= 500) EnPantalla(() => PantallaCaida(cod, null, e.Request.Uri));
                }
                catch { }
            };
            c.NavigationCompleted += (s, e) =>
            {
                int cod = 0;
                try { cod = e.HttpStatusCode; } catch { }       // runtime de Edge muy viejo: no lo informa
                string uri = navActual;
                if (cod >= 500 || (!e.IsSuccess && cod == 0 && EsFallaDeConexion(e.WebErrorStatus)))
                {
                    PantallaCaida(cod, cod == 0 ? (CoreWebView2WebErrorStatus?)e.WebErrorStatus : null, uri);
                    return;
                }
                if (e.IsSuccess) { web.Visible = true; cartel.Visible = false; webLista = true; webCaida = false; btnReintentar.Visible = false; }
                if (e.IsSuccess && compacto) EjecutarEnWeb("ponerCompacto(true)");
                if (e.IsSuccess) EnviarAutocorreccion(false);
                if (e.IsSuccess) AnunciarApp();
            };
            c.WebMessageReceived += (s, e) => MensajeDeLaPantalla(e);
            c.NewWindowRequested += (s, e) => { e.Handled = true; Abrir(e.Uri); };
            c.PermissionRequested += (s, e) =>
            {
                if (e.PermissionKind == CoreWebView2PermissionKind.ClipboardRead) e.State = CoreWebView2PermissionState.Allow;
            };
            c.DownloadStarting += (s, e) =>
            {
                descargaDesde = DateTime.Now;
                string carpeta = Programa.CarpetaDescargas();
                string nombre = Path.GetFileName(e.ResultFilePath);
                e.ResultFilePath = Path.Combine(carpeta, nombre);
                e.Handled = true;      // sin la ventanita de descargas de Edge
                var op = e.DownloadOperation;
                op.StateChanged += (s2, e2) =>
                {
                    if (op.State == CoreWebView2DownloadState.Completed)
                        MostrarAviso("Word guardado en Descargas", Path.GetFileName(op.ResultFilePath));
                    else if (op.State == CoreWebView2DownloadState.Interrupted)
                        MostrarAviso("No se pudo descargar el Word", op.InterruptReason.ToString());
                };
            };
        }

        // ¿El error de la navegación es porque no se llegó al Servidor? (no un enlace cancelado o una descarga)
        bool EsFallaDeConexion(CoreWebView2WebErrorStatus st)
        {
            if ((DateTime.Now - descargaDesde).TotalSeconds < 5) return false;
            switch (st)
            {
                case CoreWebView2WebErrorStatus.HostNameNotResolved:
                case CoreWebView2WebErrorStatus.CannotConnect:
                case CoreWebView2WebErrorStatus.ConnectionAborted:
                case CoreWebView2WebErrorStatus.ConnectionReset:
                case CoreWebView2WebErrorStatus.Disconnected:
                case CoreWebView2WebErrorStatus.ServerUnreachable:
                case CoreWebView2WebErrorStatus.Timeout:
                case CoreWebView2WebErrorStatus.ErrorHttpInvalidServerResponse:
                    return true;
                default:
                    return false;
            }
        }

        // En lugar de la página de error de Cloudflare (o la de Edge), el cartel propio con lo que pasó.
        // Cuando el Servidor vuelve a responder, el reloj de 10 s abre la pantalla de nuevo sola (urlCargada = null).
        void PantallaCaida(int codigo, CoreWebView2WebErrorStatus? error, string uri)
        {
            string motivo = MotivoCaida(codigo, error);
            bool yaEstaba = webCaida && !web.Visible;
            web.Visible = false;
            webLista = false; webCaida = true; urlCargada = null;
            btnEdge.Visible = false;
            cartel.Visible = true;
            cartel.Text = "No se pudo abrir la pantalla del Servidor.\n\n" + motivo + "\n\n" +
                          "Los audios se siguen tomando y se envían solos cuando vuelva.\n" +
                          "Se vuelve a intentar sola cada 10 segundos; no hace falta hacer nada.";
            btnReintentar.Visible = true;
            UbicarBotonesCartel();
            if (!yaEstaba)
            {
                string ruta = uri;
                Uri u;
                if (uri != null && Uri.TryCreate(uri, UriKind.Absolute, out u)) ruta = u.AbsolutePath;
                Registro.Escribir("Pantalla: no se pudo abrir " + (ruta ?? "la página") + " (" +
                    (codigo > 0 ? "el Servidor respondió " + codigo : error.HasValue ? error.Value.ToString() : "error") + ")");
            }
            try { if (web.CoreWebView2 != null) web.CoreWebView2.Stop(); } catch { }
        }

        static string MotivoCaida(int codigo, CoreWebView2WebErrorStatus? error)
        {
            if (codigo == 502 || codigo == 504 || (codigo >= 520 && codigo <= 524))
                return "El canal hasta el Servidor funciona, pero el programa del Servidor no respondió (error " + codigo + ").\n" +
                       "Puede estar reiniciándose, cerrado o muy ocupado.";
            if (codigo == 530)
                return "El canal hasta el Servidor está cerrado (error 530).\n" +
                       "La PC del Servidor puede estar apagada, sin internet o con el programa cerrado.";
            if (codigo == 503)
                return "El Servidor no está disponible en este momento (error 503).\nPuede estar reiniciándose.";
            if (codigo >= 500)
                return "El Servidor tuvo un error al abrir la pantalla (error " + codigo + ").";
            if (error == CoreWebView2WebErrorStatus.HostNameNotResolved)
                return "La dirección del Servidor ya no existe: cambia cada vez que el Servidor se reinicia.\n" +
                       "La aplicación busca la dirección nueva sola.";
            if (error == CoreWebView2WebErrorStatus.Timeout)
                return "El Servidor tardó demasiado en responder.";
            return "No se pudo conectar con el Servidor: puede no haber internet en esta PC o en la del Servidor.";
        }

        void UbicarBotonesCartel()
        {
            var b = btnReintentar.Visible ? btnReintentar : btnEdge;
            int alto = TextRenderer.MeasureText(cartel.Text ?? "", cartel.Font, new Size(Math.Max(100, cartel.Width - 40), 0),
                TextFormatFlags.WordBreak).Height;
            int y = cartel.Height / 2 + alto / 2 + 16;
            if (y + b.Height > cartel.Height) y = Math.Max(0, cartel.Height - b.Height - 8);
            btnEdge.Location = new Point((cartel.Width - btnEdge.Width) / 2, y);
            btnReintentar.Location = new Point((cartel.Width - btnReintentar.Width) / 2, y);
        }

        async Task Reintentar()
        {
            btnReintentar.Enabled = false;
            cartel.Text = "Probando la conexión con el Servidor…";
            try
            {
                await ConsultarEstado(true);
                if (urlCargada != Config.Url && (estado == Conexion.Conectado || estado == Conexion.IaNoLista)) await Entrar();
                bool sinServidor = estado == Conexion.SinConexion || estado == Conexion.Buscando;
                if (sinServidor && !web.Visible && cartel.Text == "Probando la conexión con el Servidor…")
                    cartel.Text = "El Servidor sigue sin responder.\nSe vuelve a intentar sola cada 10 segundos; no hace falta hacer nada.";
            }
            catch (Exception ex) { Registro.Escribir("Error al reintentar: " + ex.Message); }
            finally { btnReintentar.Enabled = true; }
        }

        async Task Entrar()
        {
            if (string.IsNullOrEmpty(Config.Url)) return;
            string codigo = Config.CodigoInicial;
            Config.CodigoInicial = "";
            if (codigo == "")
            {
                var r = await Servidor.Sesion(Config.Url, yaEntro);
                if (r.Codigo == 401) { PedirVincularDeNuevo(); return; }
                if (!r.Ok) { Registro.Escribir("No pude abrir la sesión: " + r.Error); return; }
                codigo = r.Texto("codigo");
            }
            string destino = Config.Url + "/entrar?codigo=" + Uri.EscapeDataString(codigo);
            urlCargada = Config.Url; yaEntro = true;
            if (webFalla) { edgePendiente = destino; return; }
            if (web.CoreWebView2 != null) web.CoreWebView2.Navigate(destino);
        }

        string edgePendiente = null;
        async void AbrirEnEdge()
        {
            var r = await Servidor.Sesion(Config.Url);
            string destino = r.Ok ? Config.Url + "/entrar?codigo=" + Uri.EscapeDataString(r.Texto("codigo")) : (edgePendiente ?? Config.Url);
            try { Process.Start("msedge.exe", "--app=\"" + destino + "\""); }
            catch { Abrir(destino); }
        }
    }
}
