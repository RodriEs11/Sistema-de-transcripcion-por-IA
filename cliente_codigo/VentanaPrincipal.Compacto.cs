// Modo compacto: ventana chica siempre visible con la cola y los avisos; íconos de sus botones.
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
        // ------------------------------------------------------------ modo compacto
        void EntrarCompacto()
        {
            if (compacto) return;
            compacto = true;
            Config.Compacto = true; GuardarConfig();
            if (WindowState == FormWindowState.Normal) { bordesNormales = Bounds; estadoNormal = FormWindowState.Normal; }
            else if (WindowState == FormWindowState.Maximized) { bordesNormales = RestoreBounds; estadoNormal = FormWindowState.Maximized; }
            WindowState = FormWindowState.Normal;
            StartPosition = FormStartPosition.Manual;
            MinimumSize = new Size(Escala(260), Escala(320));
            Bounds = BordesCompactos();
            TopMost = true;                       // siempre visible, al costado del sistema de gestión
            AjustarBarra();
            EjecutarEnWeb("ponerCompacto(true)");
        }

        void SalirCompacto()
        {
            if (!compacto) return;
            RecordarBordesCompactos();
            compacto = false;
            Config.Compacto = false; GuardarConfig();
            TopMost = false;
            MinimumSize = new Size(900, 600);
            if (bordesNormales.Width >= 900 && EnAlgunaPantalla(bordesNormales)) Bounds = bordesNormales;
            else
            {
                var wa = Screen.FromRectangle(Bounds).WorkingArea;
                Bounds = new Rectangle(wa.Left + (wa.Width - Math.Min(1400, wa.Width)) / 2, wa.Top + (wa.Height - Math.Min(900, wa.Height)) / 2,
                                      Math.Min(1400, wa.Width), Math.Min(900, wa.Height));
            }
            WindowState = estadoNormal;
            AjustarBarra();
            EjecutarEnWeb("ponerCompacto(false)");
            Activate();
        }

        // Por defecto: arriba a la derecha de la pantalla donde está la ventana. Si la persona la movió, donde la dejó.
        Rectangle BordesCompactos()
        {
            var p = (Config.BordesCompacto ?? "").Split(new[] { ',' });
            int x, y, w, h;
            if (p.Length == 4 && int.TryParse(p[0], out x) && int.TryParse(p[1], out y) && int.TryParse(p[2], out w) && int.TryParse(p[3], out h))
            {
                var r = new Rectangle(x, y, Math.Max(w, MinimumSize.Width), Math.Max(h, MinimumSize.Height));
                if (EnAlgunaPantalla(r)) return r;
            }
            var wa = Screen.FromRectangle(Bounds).WorkingArea;
            int ancho = Escala(320), alto = Math.Min(wa.Height - Escala(16), Escala(620));   // como la calculadora: más alta que ancha
            return new Rectangle(wa.Right - ancho - Escala(8), wa.Top + Escala(8), ancho, alto);
        }

        void RecordarBordesCompactos()
        {
            if (!compacto || WindowState != FormWindowState.Normal) return;
            string b = Left + "," + Top + "," + Width + "," + Height;
            if (b != Config.BordesCompacto) { Config.BordesCompacto = b; GuardarConfig(); }
        }

        static bool EnAlgunaPantalla(Rectangle r)
        {
            foreach (var s in Screen.AllScreens)
            {
                var i = Rectangle.Intersect(s.WorkingArea, r);
                if (i.Width >= 120 && i.Height >= 80) return true;
            }
            return false;
        }

        float dpi = 0;
        int Escala(int px)
        {   // la aplicación usa la escala del sistema (125 %, 150 %...)
            if (dpi <= 0) { try { using (var g = Graphics.FromHwnd(IntPtr.Zero)) dpi = g.DpiX; } catch { dpi = 96; } }
            return (int)Math.Round(px * dpi / 96.0);
        }

        void AjustarBarra()
        {
            lblDetalle.Visible = !compacto;
            TextoBotonActualizar();
            if (compacto) { BotonIcono(btnCompacto, "Agrandar"); BotonIcono(btnOpciones, "Opciones"); }
            else { BotonTexto(btnCompacto, "Compacto"); BotonTexto(btnOpciones, "Opciones ▾"); }
            ayuda.SetToolTip(btnCompacto, compacto ? "Agrandar (volver al tamaño normal)" : "Ventana chica, siempre visible al costado, con la cola y los avisos");
            ayuda.SetToolTip(btnOpciones, compacto ? "Opciones" : "");
            barra.Padding = compacto ? new Padding(10, 6, 6, 6) : new Padding(14, 6, 10, 6);
            miCompacto.Checked = compacto;
            ActualizarBarra();
            UbicarAviso();
        }

        // Botón cuadrado, sin texto, del alto de los botones con texto (sigue la escala de Windows).
        void BotonIcono(Button b, string nombre)
        {
            int h = TextRenderer.MeasureText("Ag", b.Font).Height + 11;
            b.Text = ""; b.AccessibleName = nombre;
            b.AutoSize = false; b.Padding = Padding.Empty;
            b.Size = new Size(h, h);
            b.Margin = new Padding(4, 0, 0, 0);
            b.Invalidate();
        }

        static void BotonTexto(Button b, string texto)
        {
            b.Text = texto; b.AccessibleName = null;
            b.Padding = new Padding(10, 4, 10, 4); b.AutoSize = true;
            b.Margin = new Padding(6, 0, 0, 0);
            b.Invalidate();
        }

        // Íconos de línea (como los de la pantalla web), dibujados en una grilla de 24 × 24.
        static void DibujarIcono(Graphics g, Rectangle r, string cual, Color c)
        {
            float lado = Math.Min(r.Width, r.Height) * 0.56f, k = lado / 24f;
            float x0 = r.Left + (r.Width - lado) / 2f, y0 = r.Top + (r.Height - lado) / 2f;
            Func<float, float, PointF> P = (x, y) => new PointF(x0 + x * k, y0 + y * k);
            var antes = g.SmoothingMode;
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using (var p = new Pen(c, Math.Max(1.5f, 2.1f * k)))
            {
                p.StartCap = p.EndCap = System.Drawing.Drawing2D.LineCap.Round;
                p.LineJoin = System.Drawing.Drawing2D.LineJoin.Round;
                if (cual == "agrandar")
                {   // dos flechas hacia las esquinas
                    g.DrawLines(p, new[] { P(15, 3), P(21, 3), P(21, 9) });
                    g.DrawLines(p, new[] { P(9, 21), P(3, 21), P(3, 15) });
                    g.DrawLine(p, P(21, 3), P(14, 10));
                    g.DrawLine(p, P(3, 21), P(10, 14));
                }
                else if (cual == "actualizar")
                {   // flecha hacia abajo sobre una base
                    g.DrawLine(p, P(12, 3), P(12, 15));
                    g.DrawLines(p, new[] { P(7, 10), P(12, 15), P(17, 10) });
                    g.DrawLine(p, P(5, 20), P(19, 20));
                }
                else
                {   // tres rayas (menú)
                    g.DrawLine(p, P(4, 6), P(20, 6));
                    g.DrawLine(p, P(4, 12), P(20, 12));
                    g.DrawLine(p, P(4, 18), P(20, 18));
                }
            }
            g.SmoothingMode = antes;
        }

        string TextoCorto(int pend)
        {
            switch (estado)
            {
                case Conexion.Conectado: return iaCola == 0 ? "Conectado" : "Conectado · " + iaCola + " en proceso";
                case Conexion.IaNoLista: return "IA no lista";
                case Conexion.Buscando: return "Buscando el Servidor…";
                case Conexion.SinConexion: return pend > 0 ? "Sin conexión · " + pend + " guardado" + (pend == 1 ? "" : "s") : "Sin conexión";
                default: return "Conectando…";
            }
        }
    }
}
