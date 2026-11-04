// Autocorrección de Word (Normal.dotm de esta PC) que se le pasa a la página.
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
        // ------------------------------------------------------------ autocorrección de Word (Normal.dotm de esta PC)
        void RevisarAutocorreccion()
        {
            try { if (Autocorreccion.Revisar(false)) EnviarAutocorreccion(false); }
            catch (Exception ex) { Registro.Escribir("Autocorrección: " + ex.Message); }
        }

        void EnviarAutocorreccion(bool releer)
        {
            try
            {
                Autocorreccion.Revisar(releer);
                if (web.CoreWebView2 != null)
                    web.CoreWebView2.ExecuteScriptAsync("window.ponerAutocorreccion && ponerAutocorreccion(" + Autocorreccion.Json() + ")")
                        .ContinueWith(t => { });
            }
            catch (Exception ex) { Registro.Escribir("No pude pasar la autocorrección a la pantalla: " + ex.Message); }
        }
    }
}
