// Configuración de la app que se edita desde la página: estado, cambios, carpeta del Word.
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
        // ------------------------------------------------------------ configuración (1.9)
        // La ventana de Configuración es la de la pantalla (mismo estilo que el resto): la app le pasa su estado y
        // recibe los cambios por mensajes. Si la pantalla no está cargada (sin conexión desde que se abrió la app,
        // o una página vieja sin Configuración) se muestra una ventana propia con las opciones de esta PC.
        async void AbrirConfiguracion(string seccion)
        {
            Mostrar();
            if (webLista && web.CoreWebView2 != null)
            {
                try
                {
                    string js = "(window.abrirConfiguracion && abrirConfiguracion(" + EstadoConfig() + ", "
                              + Config.Json.Serialize(seccion ?? "") + ")) ? 1 : 0";
                    string r = await web.CoreWebView2.ExecuteScriptAsync(js);
                    if (r == "1") return;
                }
                catch (Exception ex) { Registro.Escribir("No pude abrir la configuración en la pantalla: " + ex.Message); }
            }
            ConfiguracionPropia();
        }

        string EstadoConfig()
        {
            var a = Autocorreccion.Error;
            var d = new Dictionary<string, object> {
                { "version", Programa.VERSION }, { "pc", Config.Pc },
                { "inicio", Programa.IniciaConWindows() }, { "tomar", !Config.Pausado }, { "avisar", Config.AvisarListos }, { "notif", Config.NotificacionesWindows },
                { "compacto", compacto }, { "carpetaAudios", vigilante.Carpeta.TrimEnd(new[] { '\\', '/' }) },
                { "carpetaWord", Programa.CarpetaDescargas() }, { "wordPropia", Config.CarpetaWord != "" },
                { "pendientes", cola.Pendientes }, { "registro", Registro.Archivo },
                { "autoc", new Dictionary<string, object> { { "n", Autocorreccion.Entradas.Count }, { "error", a } } },
                { "servidor", Config.Url }, { "estado", lblEstado.Text + (lblDetalle.Text != "" && !compacto ? " " + lblDetalle.Text : "") },
                { "conectado", estado == Conexion.Conectado || estado == Conexion.IaNoLista },
                { "actualizacion", Actualizador.ListaHuella != null && !aplicandoActualizacion ? (Actualizador.ListaVersion != "" ? Actualizador.ListaVersion : "nueva") : "" } };
            return Config.Json.Serialize(d);
        }

        void EnviarEstadoConfig()
        {
            try
            {
                if (web.CoreWebView2 != null)
                    web.CoreWebView2.ExecuteScriptAsync("window.ponerConfigApp && ponerConfigApp(" + EstadoConfig() + ")").ContinueWith(t => { });
            }
            catch (Exception ex) { Registro.Escribir("No pude pasar la configuración a la pantalla: " + ex.Message); }
        }

        static bool EsSi(object v) { return v is bool ? (bool)v : (v + "").ToLowerInvariant() == "true"; }

        async void CambioDeConfig(string que, object valor)
        {
            try
            {
                switch (que)
                {
                    case "inicio":
                        Programa.IniciarConWindows(EsSi(valor));
                        Registro.Escribir(EsSi(valor) ? "Configuración: abrir al iniciar Windows" : "Configuración: no abrir al iniciar Windows");
                        break;
                    case "tomar": Pausar(!EsSi(valor)); break;
                    case "avisar": Config.AvisarListos = EsSi(valor); GuardarConfig(); break;
                    case "notif":
                        Config.NotificacionesWindows = EsSi(valor); GuardarConfig();
                        Registro.Escribir(Config.NotificacionesWindows ? "Configuración: notificaciones de Windows activadas" : "Configuración: notificaciones de Windows desactivadas");
                        break;
                    case "compacto": if (compacto) SalirCompacto(); else EntrarCompacto(); break;
                    case "abrirWord":
                        try { Directory.CreateDirectory(Programa.CarpetaDescargas()); } catch { }
                        Abrir(Programa.CarpetaDescargas()); break;
                    case "cambiarWord": ElegirCarpetaWord(); break;
                    case "wordPorDefecto":
                        Config.CarpetaWord = ""; GuardarConfig();
                        MostrarAviso("Carpeta de los Word", "Los Word se guardan otra vez en Descargas."); break;
                    case "registro": Abrir(Registro.Archivo); break;
                    case "autocorreccion": ReleerAutocorreccion(); break;
                    case "recargar": urlCargada = null; await Entrar(); return;
                    case "direccion":
                        string url = Servidor.Normalizar(valor + "");
                        if (url != "") await ConectarA(url);
                        break;
                    case "desvincular":     // la pantalla ya pidió la confirmación
                        Config.Desvincular(); PedirVincularDeNuevo(false); return;
                    case "actualizar": await ActualizarAhora("la persona tocó Actualizar en Configuración"); return;
                    default: return;
                }
            }
            catch (Exception ex) { Registro.Escribir("Configuración (" + que + "): " + ex.Message); }
            EnviarEstadoConfig();
        }

        void ElegirCarpetaWord()
        {
            using (var f = new FolderBrowserDialog { Description = "Carpeta donde se guardan los Word que se descargan de los informes",
                SelectedPath = Programa.CarpetaDescargas(), ShowNewFolderButton = true })
            {
                if (f.ShowDialog(this) != DialogResult.OK || string.IsNullOrEmpty(f.SelectedPath)) return;
                Config.CarpetaWord = string.Equals(f.SelectedPath.TrimEnd(new[] { '\\' }), Programa.CarpetaDescargasWindows().TrimEnd(new[] { '\\' }),
                    StringComparison.OrdinalIgnoreCase) ? "" : f.SelectedPath;
                GuardarConfig();
                Registro.Escribir("Configuración: los Word se guardan en " + Programa.CarpetaDescargas());
                MostrarAviso("Carpeta de los Word", "Los Word se guardan en " + Programa.CarpetaDescargas());
            }
        }

        void ReleerAutocorreccion()
        {
            EnviarAutocorreccion(true);
            MostrarAviso("Autocorrección de Word", Autocorreccion.Error != "" ? Autocorreccion.Error
                   : Autocorreccion.Entradas.Count + " entradas con formato leídas del Normal.dotm de esta PC.");
        }

        // Ventana propia, solo para cuando la pantalla del Servidor no está cargada.
        // Se arma a mano (cada control debajo del anterior) para que mida lo mismo en cualquier escala de Windows.
        void ConfiguracionPropia()
        {
            using (var f = new Form { Text = "Configuración — " + Config.Pc, Font = Estilo.Fuente, FormBorderStyle = FormBorderStyle.FixedDialog,
                StartPosition = FormStartPosition.CenterParent, MinimizeBox = false, MaximizeBox = false, ShowInTaskbar = false,
                BackColor = cPanel, ForeColor = cTexto, Icon = Icon, AutoScroll = true })
            {
                int margen = Escala(18), ancho = Escala(470), y = Escala(14);
                Action<Control, int> poner = (c, arriba) => { y += arriba; c.Location = new Point(margen, y); f.Controls.Add(c); y += c.Height; };
                Action<string, bool> texto = (t, negrita) =>
                {
                    var l = new Label { Text = t, AutoSize = false, Font = negrita ? Estilo.Negrita : Estilo.Fuente, ForeColor = negrita ? cTexto : cSuave };
                    l.Size = new Size(ancho, TextRenderer.MeasureText(t, l.Font, new Size(ancho, 0), TextFormatFlags.WordBreak).Height + 2);
                    poner(l, negrita ? Escala(14) : Escala(2));
                };
                Func<string, bool, CheckBox> opcion = (t, si) =>
                {
                    var c = new CheckBox { Text = t, Checked = si, AutoSize = true, ForeColor = cTexto };
                    poner(c, Escala(4));
                    return c;
                };
                Func<string, bool, Button> boton = (t, prim) =>
                {
                    var b = new Button(); VentanaVincular.Boton(b, t, prim);
                    if (!prim) { b.Font = Estilo.Fuente; b.BackColor = cPanel; b.ForeColor = cTexto; b.FlatAppearance.BorderColor = cBorde; }
                    return b;
                };
                Action<Button[]> fila = bs =>
                {   // botones uno al lado del otro; si no entran, sigue en la línea de abajo
                    int x = 0, alto = 0; y += Escala(6);
                    foreach (var b in bs)
                    {
                        var t = b.GetPreferredSize(Size.Empty); t.Width += Escala(2); b.AutoSize = false; b.Size = t;
                        if (x > 0 && x + t.Width > ancho) { x = 0; y += alto + Escala(6); alto = 0; }
                        b.Location = new Point(margen + x, y); f.Controls.Add(b);
                        x += t.Width + Escala(6); alto = Math.Max(alto, t.Height);
                    }
                    y += alto;
                };

                texto("La pantalla del Servidor no está cargada. Acá están las opciones de esta PC; el resto aparece en Configuración cuando vuelva la conexión.", false);
                texto("Esta PC", true);
                var cInicio = opcion("Abrir al iniciar Windows", Programa.IniciaConWindows());
                var cTomar = opcion("Tomar los audios del sistema automáticamente", !Config.Pausado);
                var cAvisar = opcion("Avisar cuando un informe queda listo", Config.AvisarListos);
                var cNotif = opcion("Notificaciones de Windows", Config.NotificacionesWindows);
                cInicio.CheckedChanged += (s, e) => Programa.IniciarConWindows(cInicio.Checked);
                cTomar.CheckedChanged += (s, e) => Pausar(!cTomar.Checked);
                cAvisar.CheckedChanged += (s, e) => { Config.AvisarListos = cAvisar.Checked; GuardarConfig(); };
                cNotif.CheckedChanged += (s, e) => CambioDeConfig("notif", cNotif.Checked);

                texto("Carpeta de los Word descargados", true);
                texto(Programa.CarpetaDescargas(), false);
                var lWord = f.Controls[f.Controls.Count - 1];
                var bAbrirW = boton("Abrir", false); bAbrirW.Click += (s, e) => Abrir(Programa.CarpetaDescargas());
                var bCambiarW = boton("Cambiar…", false); bCambiarW.Click += (s, e) => { ElegirCarpetaWord(); lWord.Text = Programa.CarpetaDescargas(); };
                fila(new[] { bAbrirW, bCambiarW });

                texto("Registro y autocorrección", true);
                var bReg = boton("Ver registro de envíos", false); bReg.Click += (s, e) => Abrir(Registro.Archivo);
                var bAuto = boton("Volver a leer la autocorrección de Word", false); bAuto.Click += (s, e) => ReleerAutocorreccion();
                fila(new[] { bReg, bAuto });

                texto("Servidor", true);
                texto((Config.Url != "" ? Config.Url : "Sin dirección") + " · " + lblEstado.Text, false);
                var bDir = boton("Escribir la dirección del Servidor…", false); bDir.Click += (s, e) => { f.Close(); BeginInvoke(new Action(DireccionAMano)); };
                var bRec = boton("Volver a cargar la pantalla", false); bRec.Click += (s, e) => { f.Close(); urlCargada = null; BeginInvoke(new Action(async () => await Entrar())); };
                var bDesv = boton("Desconectar esta PC…", false); bDesv.Click += (s, e) => { f.Close(); BeginInvoke(new Action(Desvincular)); };
                fila(new[] { bDir, bRec, bDesv });

                texto("Versión " + Programa.VERSION + " · Creada por Rodrigo Espíndola", false);
                y += Escala(8);
                var cerrar = boton("Listo", true); cerrar.DialogResult = DialogResult.OK;
                var tc = cerrar.GetPreferredSize(Size.Empty); cerrar.AutoSize = false; cerrar.Size = new Size(Math.Max(tc.Width, Escala(90)), tc.Height);
                cerrar.Location = new Point(margen + ancho - cerrar.Width, y); f.Controls.Add(cerrar); y += cerrar.Height;
                f.AcceptButton = cerrar; f.CancelButton = cerrar;
                var wa = Screen.FromControl(this).WorkingArea;
                f.ClientSize = new Size(Math.Min(ancho + 2 * margen, wa.Width - 40), Math.Min(y + Escala(16), wa.Height - 60));
                f.ShowDialog(this);
            }
        }
    }
}
