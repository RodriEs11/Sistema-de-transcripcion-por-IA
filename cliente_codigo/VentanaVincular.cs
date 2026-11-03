// Primer uso: conectar esta PC con el Servidor (una sola vez por PC).
using System;
using System.Drawing;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace Transcripcion
{
    class VentanaVincular : Form
    {
        readonly TextBox txtUsuario = new TextBox(), txtClave = new TextBox(), txtUrl = new TextBox();
        readonly string pc = NombrePc();
        readonly CheckBox chkInicio = new CheckBox();
        readonly Label lblPasos = new Label();
        readonly Button btnConectar = new Button(), btnCancelar = new Button();
        readonly LinkLabel lnkUrl = new LinkLabel();
        readonly Panel panelUrl = new Panel();
        static readonly Regex PcValida = new Regex(@"^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$");

        public VentanaVincular()
        {
            Text = Config.NombreVisible + " · conectar esta PC";
            Font = Estilo.Fuente;
            BackColor = Estilo.Panel;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(500, 680);
            Icon = Estilo.IconoApp();

            var t = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false,
                Padding = new Padding(28, 22, 28, 16), AutoScroll = true };
            Controls.Add(t);
            int ancho = 440;

            t.Controls.Add(new Label { Text = "Conectar esta PC", Font = Estilo.Titulo, AutoSize = true, Margin = new Padding(0, 0, 0, 4) });
            t.Controls.Add(Ayuda("Se hace una sola vez en cada computadora del trabajo. Después la aplicación se conecta sola.", ancho));

            // el nombre de la PC sale solo del nombre de Windows (aparece en la lista para saber de dónde vino cada audio)
            t.Controls.Add(Ayuda("Esta PC aparece en el sistema como «" + pc + "».", ancho));

            t.Controls.Add(Etiqueta("Tu usuario"));
            Caja(txtUsuario, ancho); t.Controls.Add(txtUsuario);
            t.Controls.Add(Etiqueta("Contraseña"));
            txtClave.UseSystemPasswordChar = true; Caja(txtClave, ancho); t.Controls.Add(txtClave);
            t.Controls.Add(Ayuda("Tu usuario y tu contraseña de transcriptor. Si en el Servidor todavía no hay " +
                                 "transcriptores, dejá el usuario vacío y escribí la contraseña del sistema.", ancho));

            t.Controls.Add(Etiqueta("Carpeta donde el sistema deja los audios"));
            var carpeta = new TextBox { Text = System.IO.Path.GetTempPath(), ReadOnly = true, Font = Estilo.Mono, BackColor = Estilo.Fondo };
            Caja(carpeta, ancho); t.Controls.Add(carpeta);
            t.Controls.Add(Ayuda("Se toman solo los archivos .wav nuevos; los demás no se tocan.", ancho));

            chkInicio.Text = "Abrir al iniciar Windows (recomendado, para no perder audios)";
            chkInicio.Checked = true; chkInicio.AutoSize = true; chkInicio.Margin = new Padding(0, 10, 0, 6);
            t.Controls.Add(chkInicio);

            lnkUrl.Text = string.IsNullOrEmpty(Config.Tema) ? "Escribí la dirección del Servidor" : "¿No encuentra el Servidor? Escribir la dirección a mano";
            lnkUrl.AutoSize = true; lnkUrl.Margin = new Padding(0, 4, 0, 4); lnkUrl.LinkColor = Estilo.Azul;
            lnkUrl.LinkClicked += (s, e) => { panelUrl.Visible = true; txtUrl.Focus(); };
            t.Controls.Add(lnkUrl);
            panelUrl.Size = new Size(ancho, 34); panelUrl.Visible = string.IsNullOrEmpty(Config.Tema); panelUrl.Margin = new Padding(0);
            Caja(txtUrl, ancho); txtUrl.Location = new Point(0, 2);
            SetCue(txtUrl, "https://….devtunnels.ms");
            panelUrl.Controls.Add(txtUrl); t.Controls.Add(panelUrl);

            lblPasos.AutoSize = false; lblPasos.Size = new Size(ancho, 70); lblPasos.ForeColor = Estilo.TextoSuave;
            lblPasos.Margin = new Padding(0, 8, 0, 8); t.Controls.Add(lblPasos);

            var botones = new FlowLayoutPanel { FlowDirection = FlowDirection.RightToLeft, Size = new Size(ancho, 44), Margin = new Padding(0) };
            Boton(btnConectar, "Conectar", true); Boton(btnCancelar, "Cancelar", false);
            botones.Controls.Add(btnConectar); botones.Controls.Add(btnCancelar);
            t.Controls.Add(botones);
            AcceptButton = btnConectar; CancelButton = btnCancelar;
            btnCancelar.Click += (s, e) => { DialogResult = DialogResult.Cancel; Close(); };
            btnConectar.Click += (s, e) => Conectar();
            Shown += (s, e) => txtUsuario.Focus();
        }

        // Nombre de Windows en el formato que acepta el Servidor: letras, números, - y _ (hasta 24).
        static string NombrePc()
        {
            string n = Regex.Replace((Environment.MachineName ?? "").ToLowerInvariant(), "[^a-z0-9_-]", "-").Trim('-', '_');
            if (n.Length > 24) n = n.Substring(0, 24).TrimEnd('-', '_');
            return PcValida.IsMatch(n) ? n : "pc";
        }

        async void Conectar()
        {
            string usuario = txtUsuario.Text.Trim(), clave = txtClave.Text;
            if (clave == "") { Paso("Escribí la contraseña.", true); txtClave.Focus(); return; }
            btnConectar.Enabled = false; UseWaitCursor = true;
            try
            {
                string url = Servidor.Normalizar(txtUrl.Text);
                if (url == "")
                {
                    Paso("Buscando el Servidor…", false);
                    url = await Servidor.BuscarDireccion();
                    if (url == null)
                    {
                        Paso("No encontré el Servidor. Puede estar apagado o sin internet en este momento. " +
                             "Probá de nuevo en unos minutos o pegá abajo la dirección del Servidor.", true);
                        panelUrl.Visible = true; return;
                    }
                }
                Paso("✓ Servidor encontrado\nComprobando la contraseña…", false);
                var r = await Servidor.Vincular(url, pc, usuario, clave);
                if (!r.Ok)
                {
                    if (r.Codigo == 0) Registro.Escribir("No pude comunicarme con " + url + ": " + r.Error);
                    Paso(r.Codigo == 0 ? "No pude comunicarme con el Servidor.\nRevisá que la dirección esté bien copiada y que haya internet." : r.Error, true);
                    return;
                }
                Config.Pc = pc; Config.Url = url; Config.Llave = r.Texto("llave"); Config.Guardar();
                Config.CodigoInicial = r.Texto("codigo");   // la página abre ya con este usuario (no se lo pide otra vez)
                Paso("✓ Servidor encontrado\n✓ Contraseña correcta: esta PC quedó autorizada\nProbando la conexión…", false);
                var e2 = await Servidor.Estado(url);
                if (!e2.Ok) { Paso("La PC quedó autorizada pero la prueba falló: " + e2.Error, true); return; }
                Programa.IniciarConWindows(chkInicio.Checked);
                Registro.Escribir("PC vinculada como " + pc + " con " + url);
                DialogResult = DialogResult.OK; Close();
            }
            finally { btnConectar.Enabled = true; UseWaitCursor = false; }
        }

        void Paso(string texto, bool error)
        {
            lblPasos.Text = texto;
            lblPasos.ForeColor = error ? Estilo.Rojo : Estilo.TextoSuave;
        }

        static Label Etiqueta(string t)
        {
            return new Label { Text = t, AutoSize = true, Font = Estilo.Negrita, Margin = new Padding(0, 12, 0, 4) };
        }

        static Label Ayuda(string t, int ancho)
        {
            return new Label { Text = t, AutoSize = true, MaximumSize = new Size(ancho, 0), ForeColor = Estilo.TextoSuave,
                Font = Estilo.Chica, Margin = new Padding(0, 3, 0, 0) };
        }

        static void Caja(TextBox t, int ancho) { t.Width = ancho; t.Margin = new Padding(0); }

        public static void Boton(Button b, string texto, bool principal)
        {
            b.Text = texto; b.AutoSize = true; b.Padding = new Padding(10, 4, 10, 4); b.Margin = new Padding(8, 6, 0, 0);
            b.FlatStyle = FlatStyle.Flat; b.Cursor = Cursors.Hand;
            b.FlatAppearance.BorderColor = principal ? Estilo.Azul : Estilo.Borde;
            b.BackColor = principal ? Estilo.Azul : Estilo.Panel;
            b.ForeColor = principal ? Color.White : Estilo.Texto;
            if (principal) b.Font = Estilo.Negrita;
        }

        [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, string l);
        static void SetCue(TextBox t, string texto)
        {
            t.HandleCreated += (s, e) => { try { SendMessage(t.Handle, 0x1501, (IntPtr)1, texto); } catch { } };
        }
    }
}
