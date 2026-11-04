// Aviso dentro de la ventana (abajo a la derecha).
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
        // ------------------------------------------------------------ aviso dentro de la ventana
        void ArmarAviso()
        {
            aviso.Size = new Size(360, 78); aviso.BackColor = Estilo.Oscuro; aviso.Visible = false;
            aviso.Anchor = AnchorStyles.Bottom | AnchorStyles.Right; aviso.Padding = new Padding(14, 10, 14, 10);
            avisoTitulo.Dock = DockStyle.Top; avisoTitulo.Height = 22; avisoTitulo.ForeColor = Color.White; avisoTitulo.Font = Estilo.Negrita;
            avisoTexto.Dock = DockStyle.Fill; avisoTexto.ForeColor = Color.FromArgb(0xcf, 0xcd, 0xc6);
            aviso.Controls.Add(avisoTexto); aviso.Controls.Add(avisoTitulo);
            aviso.Click += (s, e) => aviso.Visible = false;
            avisoTexto.Click += (s, e) => aviso.Visible = false;
            Resize += (s, e) => UbicarAviso();
        }

        void UbicarAviso()
        {
            aviso.Width = Math.Max(240, Math.Min(360, ClientSize.Width - 24));
            aviso.Location = new Point(ClientSize.Width - aviso.Width - 20, ClientSize.Height - aviso.Height - 20);
        }

        void MostrarAviso(string titulo, string texto)
        {
            avisoTitulo.Text = titulo; avisoTexto.Text = texto;
            UbicarAviso(); aviso.Visible = true; aviso.BringToFront();
            relojAviso.Stop(); relojAviso.Start();
            if (!Visible || WindowState == FormWindowState.Minimized)
                Notificaciones.Globo(bandeja, 5000, titulo, texto);
        }
    }
}
