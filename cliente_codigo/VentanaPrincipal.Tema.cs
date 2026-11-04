// Tema claro / oscuro de la barra y de la ventana; guardar la configuración.
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
        // ------------------------------------------------------------ tema claro / oscuro
        void AplicarTema(bool oscuro)
        {
            cFondo = oscuro ? Color.FromArgb(0x14, 0x14, 0x13) : Estilo.Fondo;
            cPanel = oscuro ? Color.FromArgb(0x1b, 0x1b, 0x1a) : Estilo.Panel;
            cTexto = oscuro ? Color.FromArgb(0xeb, 0xea, 0xe5) : Estilo.Texto;
            cSuave = oscuro ? Color.FromArgb(0xa1, 0x9f, 0x98) : Estilo.TextoSuave;
            cLinea = oscuro ? Color.FromArgb(0x33, 0x32, 0x2e) : Estilo.Linea;
            cBorde = oscuro ? Color.FromArgb(0x45, 0x44, 0x3f) : Estilo.Borde;
            cFondoAmbar = oscuro ? Color.FromArgb(0x3a, 0x30, 0x10) : Estilo.FondoAmbar;
            cFondoRojo = oscuro ? Color.FromArgb(0x3d, 0x1f, 0x1c) : Estilo.FondoRojo;
            BackColor = cFondo;
            web.DefaultBackgroundColor = cFondo;
            cartel.BackColor = cFondo; cartel.ForeColor = cSuave;
            lblEstado.ForeColor = cTexto; lblDetalle.ForeColor = cSuave;
            foreach (var b in new[] { btnWord, btnCompacto, btnOpciones })
            {
                b.BackColor = cPanel; b.ForeColor = cTexto; b.FlatAppearance.BorderColor = cBorde;
                b.FlatAppearance.MouseOverBackColor = oscuro ? Color.FromArgb(0x26, 0x26, 0x24) : Color.FromArgb(0xee, 0xed, 0xe9);
            }
            ActualizarBarra();
            barra.Invalidate();
            TituloOscuro(oscuro);
        }

        [DllImport("user32.dll")] static extern short GetAsyncKeyState(int tecla);

        // ¿Hay un botón del mouse apretado ahora (en cualquier ventana)?
        static bool BotonApretado()
        {
            try { return (GetAsyncKeyState(0x01) & 0x8000) != 0 || (GetAsyncKeyState(0x02) & 0x8000) != 0 || (GetAsyncKeyState(0x04) & 0x8000) != 0; }
            catch { return false; }
        }

        static bool SobreBoton(Control b, Point pantalla)
        {
            return b.Visible && b.RectangleToScreen(b.ClientRectangle).Contains(pantalla);
        }

        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h, int atributo, ref int valor, int tam);

        // Barra de título oscura (Windows 10 2004 o posterior y Windows 11; en otros no hace nada).
        void TituloOscuro(bool oscuro)
        {
            if (!IsHandleCreated) return;
            try { int v = oscuro ? 1 : 0; DwmSetWindowAttribute(Handle, 20, ref v, 4); } catch { }
        }

        void GuardarConfig()
        {
            try { Config.Guardar(); }
            catch (Exception ex) { Registro.Escribir("No pude guardar la configuración: " + ex.Message); }
        }
    }
}
