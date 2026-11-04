// Barra de estado propia (arriba de la página): punto, textos, botones y menú Opciones.
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
        // ------------------------------------------------------------ barra de estado
        void ArmarBarra()
        {
            barra.Dock = DockStyle.Top; barra.Height = 46; barra.BackColor = Estilo.Panel;
            barra.Padding = new Padding(14, 6, 10, 6);
            barra.ColumnCount = 8; barra.RowCount = 1;
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 20));
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            barra.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            barra.Paint += (s, e) => { using (var p = new Pen(cLinea)) e.Graphics.DrawLine(p, 0, barra.Height - 1, barra.Width, barra.Height - 1); };

            punto.Size = new Size(12, 12); punto.Anchor = AnchorStyles.None; punto.Margin = new Padding(0);
            punto.Paint += (s, e) =>
            {
                e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                using (var b = new SolidBrush(ColorEstado())) e.Graphics.FillEllipse(b, 0, 0, 11, 11);
            };
            lblEstado.AutoSize = true; lblEstado.Font = Estilo.Negrita; lblEstado.Anchor = AnchorStyles.Left; lblEstado.Margin = new Padding(4, 0, 6, 0);
            lblDetalle.AutoSize = true; lblDetalle.ForeColor = Estilo.TextoSuave; lblDetalle.Anchor = AnchorStyles.Left; lblDetalle.AutoEllipsis = true;
            // 1.10: la casilla "Tomar los audios del sistema automáticamente" ya no está en la barra:
            // se cambia en Configuración (y en el menú junto al reloj).

            VentanaVincular.Boton(btnActualizar, "Actualizar", true);
            btnActualizar.Anchor = AnchorStyles.Right; btnActualizar.Margin = new Padding(6, 0, 6, 0); btnActualizar.Visible = false;
            btnActualizar.Click += async (s, e) => await ActualizarAhora("la persona tocó Actualizar");

            VentanaVincular.Boton(btnWord, "Word descargados", false);
            btnWord.Anchor = AnchorStyles.Right; btnWord.Margin = new Padding(6, 0, 0, 0);
            btnWord.Click += (s, e) => Abrir(Programa.CarpetaDescargas());
            VentanaVincular.Boton(btnCompacto, "Compacto", false);
            btnCompacto.Anchor = AnchorStyles.Right; btnCompacto.Margin = new Padding(6, 0, 0, 0);
            btnCompacto.Click += (s, e) => { if (compacto) SalirCompacto(); else EntrarCompacto(); };
            ayuda.SetToolTip(btnCompacto, "Ventana chica, siempre visible al costado, con la cola y los avisos");
            VentanaVincular.Boton(btnOpciones, "Opciones ▾", false);
            btnOpciones.Anchor = AnchorStyles.Right; btnOpciones.Margin = new Padding(6, 0, 0, 0);
            // 1.9: lo que es configuración (abrir con Windows, registro, dirección, autocorrección, desconectar...)
            // está ahora en la ventana de Configuración; en el menú quedan las acciones de todos los días.
            var menu = new ContextMenuStrip { Font = Estilo.Fuente };
            menu.Items.Add(new ToolStripMenuItem("Configuración…", null, (s, e) => AbrirConfiguracion(null)) { Font = Estilo.Negrita,
                ToolTipText = "Abrir con Windows, toma de audios, carpeta de los Word, registro de envíos, Servidor, pantalla y audio" });
            menu.Items.Add("Cargar audio…", null, (s, e) => CargarAudio());
            menu.Items.Add("Volver a cargar la pantalla", null, async (s, e) => { urlCargada = null; await Entrar(); });
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(new ToolStripMenuItem("Cerrar sesión", null, (s, e) => CambiarDeUsuario())
                { ToolTipText = "Para que entre otra persona: la aplicación sigue abierta y pide usuario y contraseña" });
            menu.Items.Add(new ToolStripMenuItem("Salir", null, (s, e) => Salir())
                { ToolTipText = "Cierra la aplicación (deja de tomar audios hasta que se vuelva a abrir)" });
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(new ToolStripMenuItem("Versión " + Programa.VERSION) { Enabled = false });
            menu.Items.Add(new ToolStripMenuItem("Creada por Rodrigo Espíndola") { Enabled = false });
            // El menú se abre y se cierra con el mismo botón, y se cierra al hacer clic en cualquier otro lado
            // (también en la pantalla del Servidor, que es otra ventana y no le avisa al menú).
            bool cerroSobreBoton = false; DateTime menuCerradoEn = DateTime.MinValue;
            var relojMenu = new System.Windows.Forms.Timer { Interval = 80 };
            relojMenu.Tick += (s, e) =>
            {
                if (!menu.Visible) { relojMenu.Stop(); return; }
                if (!BotonApretado()) return;
                var pos = Cursor.Position;
                if (menu.Bounds.Contains(pos) || SobreBoton(btnOpciones, pos)) return;
                menu.Close(ToolStripDropDownCloseReason.AppClicked);
            };
            menu.Opened += (s, e) => relojMenu.Start();
            menu.Closed += (s, e) =>
            {
                relojMenu.Stop();
                menuCerradoEn = DateTime.Now;
                cerroSobreBoton = e.CloseReason == ToolStripDropDownCloseReason.AppClicked && SobreBoton(btnOpciones, Cursor.Position);
            };
            btnOpciones.Click += (s, e) =>
            {
                if (menu.Visible) { menu.Close(ToolStripDropDownCloseReason.AppClicked); return; }
                if (cerroSobreBoton && (DateTime.Now - menuCerradoEn).TotalSeconds < 2) { cerroSobreBoton = false; return; }  // el clic era para cerrarlo
                cerroSobreBoton = false;
                menu.Show(btnOpciones, new Point(btnOpciones.Width - menu.Width, btnOpciones.Height));
            };
            Move += (s, e) => { if (menu.Visible) menu.Close(ToolStripDropDownCloseReason.AppFocusChange); };
            // en el modo compacto estos dos botones son solo un ícono (se dibuja encima del botón vacío)
            btnCompacto.Paint += (s, e) => { if (compacto) DibujarIcono(e.Graphics, btnCompacto.ClientRectangle, "agrandar", btnCompacto.ForeColor); };
            btnOpciones.Paint += (s, e) => { if (compacto) DibujarIcono(e.Graphics, btnOpciones.ClientRectangle, "menu", btnOpciones.ForeColor); };
            btnActualizar.Paint += (s, e) => { if (compacto) DibujarIcono(e.Graphics, btnActualizar.ClientRectangle, "actualizar", btnActualizar.ForeColor); };

            barra.Controls.Add(punto, 0, 0);
            barra.Controls.Add(lblEstado, 1, 0);
            barra.Controls.Add(lblDetalle, 2, 0);
            barra.Controls.Add(btnActualizar, 3, 0);
            barra.Controls.Add(btnWord, 5, 0);
            barra.Controls.Add(btnCompacto, 6, 0);
            barra.Controls.Add(btnOpciones, 7, 0);
            PonerEstado(Conexion.Iniciando, null);
        }

        Color ColorEstado()
        {
            switch (estado)
            {
                case Conexion.Conectado: return Estilo.Verde;
                case Conexion.IaNoLista: return Estilo.Naranja;
                case Conexion.SinConexion: return Estilo.Rojo;
                default: return Estilo.Ambar;
            }
        }

        int iaCola = 0;
        void PonerEstado(Conexion e, Respuesta r)
        {
            estado = e;
            if (r != null && r.Datos != null && r.Datos.ContainsKey("cola")) int.TryParse(r.Texto("cola"), out iaCola);
            ActualizarBarra();
        }

        void ActualizarBarra()
        {
            int pend = cola.Pendientes;
            string detalle;
            switch (estado)
            {
                case Conexion.Conectado:
                    lblEstado.Text = "Conectado al Servidor";
                    detalle = "· IA lista · " + (iaCola == 0 ? "nada en cola" : iaCola + " en proceso");
                    barra.BackColor = cPanel; break;
                case Conexion.IaNoLista:
                    lblEstado.Text = "Conectado, pero la IA no está lista";
                    detalle = "· los audios llegan y esperan en la cola";
                    barra.BackColor = cPanel; break;
                case Conexion.Buscando:
                    lblEstado.Text = "Buscando el Servidor…";
                    detalle = "se reconecta solo, no hace falta hacer nada";
                    barra.BackColor = cFondoAmbar; break;
                case Conexion.SinConexion:
                    lblEstado.Text = "Sin conexión con el Servidor";
                    detalle = pend > 0 ? "· " + pend + (pend == 1 ? " audio guardado" : " audios guardados") + " en esta PC, se envían solos cuando vuelva"
                                       : "· reintentando cada 10 segundos";
                    barra.BackColor = cFondoRojo; break;
                default:
                    lblEstado.Text = "Conectando…"; detalle = ""; barra.BackColor = cPanel; break;
            }
            if (compacto) lblEstado.Text = TextoCorto(pend);
            if (estado != Conexion.SinConexion && pend > 0) detalle += " · enviando " + pend;
            if (Config.Pausado) detalle += " · toma de audios en pausa";
            lblDetalle.Text = detalle;
            punto.Invalidate();
            var color = ColorEstado();
            bandeja.Icon = Estilo.Icono(color);
            string tip = "Transcripción · " + Config.Pc + " · " + (compacto ? TextoCorto(pend) : lblEstado.Text);
            bandeja.Text = tip.Length > 63 ? tip.Substring(0, 63) : tip;
        }
    }
}
