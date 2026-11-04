// Ícono junto al reloj: menú, mostrar la ventana, otra instancia, pausar, salir y cambiar de usuario.
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
        // ------------------------------------------------------------ ícono junto al reloj
        void ArmarBandeja()
        {
            var m = new ContextMenuStrip { Font = Estilo.Fuente };
            var abrir = new ToolStripMenuItem("Abrir Transcripción", null, (s, e) => Mostrar()) { Font = Estilo.Negrita };
            m.Items.Add(abrir);
            miCompacto.Checked = compacto;
            miCompacto.Click += (s, e) => { Mostrar(); if (compacto) SalirCompacto(); else EntrarCompacto(); };
            m.Items.Add(miCompacto);
            miPausar.Checked = Config.Pausado;
            miPausar.Click += (s, e) => Pausar(!Config.Pausado);
            m.Items.Add(miPausar);
            m.Items.Add("Cargar audio…", null, (s, e) => CargarAudio());
            m.Items.Add("Ver registro de envíos", null, (s, e) => Abrir(Registro.Archivo));
            m.Items.Add("Configuración…", null, (s, e) => AbrirConfiguracion(null));
            m.Items.Add(new ToolStripSeparator());
            m.Items.Add("Cerrar sesión", null, (s, e) => { Mostrar(); CambiarDeUsuario(); });
            m.Items.Add("Salir", null, (s, e) => Salir());
            bandeja.ContextMenuStrip = m;
            bandeja.Icon = Estilo.Icono(Estilo.Ambar);
            bandeja.Text = Config.NombreVisible;
            bandeja.Visible = true;
            bandeja.DoubleClick += (s, e) => Mostrar();
            bandeja.BalloonTipClicked += (s, e) => Mostrar();
        }

        void Mostrar()
        {
            permitirMostrar = true;
            Show();
            if (WindowState == FormWindowState.Minimized) WindowState = compacto ? FormWindowState.Normal : estadoNormal;
            Activate(); BringToFront();
        }

        void EscucharOtraInstancia()
        {
            var t = new Thread(() =>
            {
                while (true) { Programa.SenalMostrar.WaitOne(); EnPantalla(Mostrar); }
            }) { IsBackground = true };
            t.Start();
        }

        void Pausar(bool si)
        {
            Config.Pausado = si; GuardarConfig();
            miPausar.Checked = si;
            Registro.Escribir(si ? "Toma de audios en pausa" : "Toma de audios activada");
            ActualizarBarra();
        }

        async Task<bool> PuedeCerrarWeb()
        {
            if (!webLista || web.CoreWebView2 == null) return true;
            try
            {
                var consulta = web.CoreWebView2.ExecuteScriptAsync("typeof actual==='undefined' || actual===null");
                if (await Task.WhenAny(consulta, Task.Delay(3000)) != consulta) return false;
                return await consulta == "true";
            }
            catch { return false; } // no cerrar una pantalla cuyo estado no pudimos comprobar
        }

        async void Salir()
        {
            if (!await PuedeCerrarWeb())
            {
                Mostrar();
                MostrarAviso("Primero cerrá el estudio", "Usá Cerrar estudio para confirmar que tus cambios quedaron guardados antes de salir.");
                return;
            }
            if (cola.Pendientes > 0 &&
                MessageBox.Show(this, "Hay audios que todavía no llegaron al Servidor. Si salís, se envían la próxima vez que abras la aplicación.\n\n¿Salir igual?",
                    "Transcripción", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
            saliendo = true;
            Hide();                        // se cierra enseguida: no se ve la pantalla de entrar
            bandeja.Visible = false;
            await CerrarSesionUsuario(true);
            vigilante.Dispose();
            Application.Exit();
        }

        // «Cerrar sesión»: la persona sale y la app queda abierta pidiendo usuario y contraseña.
        async void CambiarDeUsuario()
        {
            if (!await CerrarSesionUsuario())
                MostrarAviso("No hay una sesión abierta", "Este Servidor no tiene transcriptores, o la pantalla todavía no cargó.");
        }

        // Cierra la sesión del transcriptor en la página (window.salirDeSesion de web/index.html). La página cierra
        // antes el estudio abierto guardando sus cambios; si no puede, no cierra la sesión. Devuelve true si había una
        // sesión de transcriptor y se pidió cerrarla. Con un Servidor sin transcriptores (o una página anterior) no
        // hace nada. alSalir: la app se está cerrando; la página avisa al Servidor sin mostrar la pantalla de entrar.
        async Task<bool> CerrarSesionUsuario(bool alSalir = false)
        {
            if (!webLista || web.CoreWebView2 == null) return false;
            try
            {
                var pedido = web.CoreWebView2.ExecuteScriptAsync("typeof window.salirDeSesion==='function' && window.salirDeSesion("
                    + (alSalir ? "{navegar:false}" : "") + ")===true");
                if (await Task.WhenAny(pedido, Task.Delay(3000)) != pedido) return false;
                bool cerro = await pedido == "true";
                if (cerro)
                {
                    Registro.Escribir(alSalir ? "Aplicación cerrada: se cierra la sesión del transcriptor."
                                              : "Se cierra la sesión del transcriptor.");
                    if (alSalir) await Task.Delay(400);        // que el aviso al Servidor salga antes de terminar
                }
                return cerro;
            }
            catch (Exception ex) { Registro.Escribir("No se pudo cerrar la sesión del transcriptor: " + ex.Message); return false; }
        }
    }
}
