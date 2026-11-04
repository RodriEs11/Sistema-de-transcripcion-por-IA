// Actualización automática de la app cuando no se usa.
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
        // ------------------------------------------------------------ actualización automática
        [StructLayout(LayoutKind.Sequential)] struct UltimaEntrada { public uint Tam; public uint Tiempo; }
        [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref UltimaEntrada u);

        // Tiempo desde la última vez que se tocó el teclado o el mouse (en cualquier programa).
        static TimeSpan Inactivo()
        {
            try
            {
                var u = new UltimaEntrada { Tam = (uint)Marshal.SizeOf(typeof(UltimaEntrada)) };
                if (!GetLastInputInfo(ref u)) return TimeSpan.Zero;
                return TimeSpan.FromMilliseconds(unchecked((uint)Environment.TickCount - u.Tiempo));
            }
            catch { return TimeSpan.Zero; }
        }

        void TextoBotonActualizar()
        {
            btnActualizar.Visible = Actualizador.ListaHuella != null && !aplicandoActualizacion;
            string v = Actualizador.ListaVersion;
            if (compacto) BotonIcono(btnActualizar, "Actualizar");
            else
            {
                BotonTexto(btnActualizar, v != "" && v != Programa.VERSION ? "Actualizar a la " + v : "Actualizar");
                btnActualizar.Margin = new Padding(6, 0, 6, 0);
            }
            ayuda.SetToolTip(btnActualizar, "Hay una versión nueva de la aplicación. Se instala sola cuando no la estés usando, " +
                                            "o ahora con este botón (tarda unos segundos; no se pierde nada).");
        }

        void ActualizacionLista()
        {
            TextoBotonActualizar();
            if (!avisoActualizacionMostrado && Visible && !Actualizador.SoloReiniciar)
            {
                avisoActualizacionMostrado = true;
                MostrarAviso("Hay una versión nueva de la aplicación",
                    "Se instala sola cuando no la estés usando, o tocá «Actualizar» arriba.");
            }
        }

        // Cada 10 s: si hay una versión lista y nadie está usando la app, instalarla.
        async Task RevisarSiActualizar()
        {
            if (Actualizador.ListaHuella == null || aplicandoActualizacion || pidiendoVincular) return;
            if (cola.Pendientes > 0) return;                    // no cortar un audio a medio enviar
            bool libre;
            var quieto = Inactivo();
            if (!Visible || WindowState == FormWindowState.Minimized) libre = true;
            else if (quieto >= TimeSpan.FromMinutes(5)) libre = true;
            else if (!ContainsFocus && quieto >= TimeSpan.FromMinutes(1))
                // compacta al costado, o la ventana grande sin usar hace 10 minutos
                libre = compacto || (DateTime.Now - sinFocoDesde) >= TimeSpan.FromMinutes(10);
            else libre = false;
            if (libre) await ActualizarAhora("nadie la estaba usando");
        }

        async Task ActualizarAhora(string motivo)
        {
            if (aplicandoActualizacion || Actualizador.ListaHuella == null) return;
            aplicandoActualizacion = true;
            if (!await PuedeCerrarWeb())
            {
                aplicandoActualizacion = false;
                if (motivo != "nadie la estaba usando")
                    MostrarAviso("Actualización pendiente", "Primero cerrá el estudio para confirmar el guardado de tus cambios.");
                return;
            }
            TextoBotonActualizar();
            Registro.Escribir("Actualización: se instala la versión " + Actualizador.ListaVersion + " (" + motivo + ").");
            bool oculta = !Visible || WindowState == FormWindowState.Minimized;
            if (!Actualizador.AplicarYReabrir(oculta))
            {
                aplicandoActualizacion = false;
                TextoBotonActualizar();
                MostrarAviso("No se pudo actualizar la aplicación", "Sigue funcionando con esta versión. " + Actualizador.UltimoError);
                return;
            }
            saliendo = true;
            bandeja.Visible = false;
            vigilante.Dispose();
            Application.Exit();
        }
    }
}
