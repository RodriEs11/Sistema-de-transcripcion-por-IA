// Ventana principal: barra de estado propia + la interfaz del Servidor (WebView2) + ícono junto al reloj.
// Modo compacto: ventana chica, siempre visible al costado, que muestra solo la cola y los avisos;
// al hacer clic en un caso (o en "Agrandar") vuelve al tamaño normal y lo abre.
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
    // Reloj que llama a la ventana cada tanto aunque esté escondida (arranque con Windows).
    class RelojUi
    {
        readonly Control dueno;
        readonly int ms;
        System.Threading.Timer t;
        public event EventHandler Tick;
        public RelojUi(Control c, int milisegundos) { dueno = c; ms = milisegundos; }
        public void Start()
        {
            if (t != null) return;
            t = new System.Threading.Timer(_ =>
            {
                try
                {
                    if (dueno.IsHandleCreated && !dueno.IsDisposed)
                        dueno.BeginInvoke(new Action(() => { var h = Tick; if (h != null && t != null) h(this, EventArgs.Empty); }));
                }
                catch { }
            }, null, ms, ms);
        }
        public void Stop() { if (t != null) { t.Dispose(); t = null; } }
    }

    enum Conexion { Iniciando, Conectado, IaNoLista, Buscando, SinConexion }

    class VentanaPrincipal : Form
    {
        readonly WebView2 web = new WebView2();
        readonly Label cartel = new Label();
        readonly Button btnEdge = new Button();
        readonly Panel punto = new Panel();
        readonly Label lblEstado = new Label(), lblDetalle = new Label();
        readonly CheckBox chkTomar = new CheckBox();
        readonly Button btnWord = new Button(), btnOpciones = new Button(), btnCompacto = new Button(), btnActualizar = new Button();
        bool aplicandoActualizacion = false, avisoActualizacionMostrado = false;
        DateTime sinFocoDesde = DateTime.Now;
        readonly ToolStripMenuItem miCompacto = new ToolStripMenuItem("Modo compacto (siempre visible)");
        readonly ToolTip ayuda = new ToolTip();
        bool compacto = false;
        Rectangle bordesNormales = Rectangle.Empty;
        FormWindowState estadoNormal = FormWindowState.Maximized;
        // colores de la barra (claros u oscuros, según el tema que se elija en la pantalla)
        Color cFondo = Estilo.Fondo, cPanel = Estilo.Panel, cTexto = Estilo.Texto, cSuave = Estilo.TextoSuave,
              cLinea = Estilo.Linea, cBorde = Estilo.Borde, cFondoAmbar = Estilo.FondoAmbar, cFondoRojo = Estilo.FondoRojo;
        readonly TableLayoutPanel barra = new TableLayoutPanel();
        readonly NotifyIcon bandeja = new NotifyIcon();
        readonly ToolStripMenuItem miPausar = new ToolStripMenuItem("Pausar la toma de audios");
        readonly ToolStripMenuItem miInicio = new ToolStripMenuItem("Abrir al iniciar Windows");
        readonly Panel aviso = new Panel();
        readonly Label avisoTitulo = new Label(), avisoTexto = new Label();
        readonly System.Windows.Forms.Timer relojAviso = new System.Windows.Forms.Timer { Interval = 9000 };
        readonly RelojUi relojEstado;      // cada 10 s: estado del Servidor (anda también con la ventana escondida)

        readonly Vigilante vigilante = new Vigilante();
        readonly ColaEnvio cola = new ColaEnvio();
        readonly Dictionary<string, string> estadosCasos = new Dictionary<string, string>();
        bool primeraLectura = true, webLista = false, webFalla = false, saliendo = false;
        int consultando = 0;   // consultas al Servidor en curso (una forzada puede ir junto a otra)
        bool avisoBandejaMostrado = false, pidiendoVincular = false;
        string urlCargada = null;
        Conexion estado = Conexion.Iniciando;
        readonly bool iniciarOculta;
        bool permitirMostrar, webIniciada, iniciado;

        // Al iniciar Windows arranca escondida (solo el ícono junto al reloj) y ya toma audios.
        protected override void SetVisibleCore(bool value)
        {
            if (iniciarOculta && !permitirMostrar)
            {
                value = false;
                if (!IsHandleCreated) CreateHandle();
            }
            base.SetVisibleCore(value);
        }

        public VentanaPrincipal(bool oculta)
        {
            iniciarOculta = oculta;
            relojEstado = new RelojUi(this, 10000);
            Text = "Transcripción — " + Config.Pc;
            Font = Estilo.Fuente;
            BackColor = Estilo.Fondo;
            AutoScaleMode = AutoScaleMode.Font;
            MinimumSize = new Size(900, 600);
            Size = new Size(1400, 900);
            StartPosition = FormStartPosition.CenterScreen;
            WindowState = FormWindowState.Maximized;
            Icon = Estilo.IconoApp();
            KeyPreview = true;

            ArmarBarra();
            ArmarAviso();

            web.Dock = DockStyle.Fill;
            web.DefaultBackgroundColor = Estilo.Fondo;
            web.Visible = false;
            cartel.Dock = DockStyle.Fill; cartel.TextAlign = ContentAlignment.MiddleCenter;
            cartel.ForeColor = Estilo.TextoSuave; cartel.Font = new Font("Segoe UI", 11f);
            cartel.Text = "Conectando con el Servidor…";
            VentanaVincular.Boton(btnEdge, "Abrir en Microsoft Edge", true);
            btnEdge.Visible = false; btnEdge.Anchor = AnchorStyles.None;
            btnEdge.Click += (s, e) => AbrirEnEdge();
            cartel.Controls.Add(btnEdge);
            cartel.Resize += (s, e) => btnEdge.Location = new Point((cartel.Width - btnEdge.Width) / 2, cartel.Height / 2 + 40);

            Controls.Add(web);
            Controls.Add(cartel);
            Controls.Add(barra);
            Controls.Add(aviso);
            aviso.BringToFront();

            ArmarBandeja();
            if (Config.Oscuro) AplicarTema(true);
            if (Config.Compacto) EntrarCompacto();
            HandleCreated += (s, e) => TituloOscuro(Config.Oscuro);
            ResizeEnd += (s, e) => RecordarBordesCompactos();

            vigilante.AudioListo += (nombre, datos, huella) =>
            {
                try { cola.Agregar(nombre, datos, huella); }
                catch (Exception ex) { Registro.Escribir("No pude guardar " + nombre + ": " + ex.Message); }
                EnPantalla(() => MostrarAviso("Audio nuevo tomado del sistema",
                    nombre + " · " + (datos.Length / 1024.0 / 1024.0).ToString("0.0") + " MB · enviando al Servidor…"));
            };
            cola.Enviado += (nombre, caso, dup) => EnPantalla(() =>
            {
                MostrarAviso(dup ? "Este audio ya estaba en el Servidor" : "Audio enviado al Servidor",
                    nombre + (dup ? " · se abre el caso que ya existía" : " · transcribiendo… te aviso cuando esté listo"));
                ActualizarBarra();
            });
            cola.Rechazado += (nombre, motivo) => EnPantalla(() => MostrarAviso("El Servidor no aceptó " + nombre, motivo));
            cola.LlaveInvalida += () => EnPantalla(PedirVincularDeNuevo);
            cola.PendientesCambio += n => EnPantalla(ActualizarBarra);

            relojEstado.Tick += async (s, e) => { await ConsultarEstado(); await RevisarSiActualizar(); RevisarAutocorreccion(); };
            Actualizador.Preparada += () => EnPantalla(ActualizacionLista);
            Activated += (s, e) => sinFocoDesde = DateTime.MaxValue;
            Deactivate += (s, e) => sinFocoDesde = DateTime.Now;
            relojAviso.Tick += (s, e) => { aviso.Visible = false; relojAviso.Stop(); };

            HandleCreated += async (s, e) =>
            {   // lo que funciona aunque la ventana esté escondida (al iniciar Windows)
                if (iniciado) return;
                iniciado = true;
                Actualizador.Confirmar();     // si es una versión recién instalada: abrió bien
                vigilante.Iniciar();
                cola.Iniciar();
                EscucharOtraInstancia();
                await ConsultarEstado();
                relojEstado.Start();
            };
            Shown += async (s, e) =>
            {   // la pantalla del Servidor se carga la primera vez que se muestra la ventana
                if (webIniciada) return;
                webIniciada = true;
                await IniciarWeb();
                urlCargada = null;
                await Entrar();
            };
            FormClosing += (s, e) =>
            {
                if (!saliendo && e.CloseReason == CloseReason.UserClosing)
                {   // cerrar = esconder; sigue tomando audios
                    e.Cancel = true; Hide();
                    if (!avisoBandejaMostrado)
                    {
                        avisoBandejaMostrado = true;
                        bandeja.ShowBalloonTip(5000, "Transcripción sigue funcionando",
                            "Los audios se siguen enviando. Para abrirla, hacé doble clic en el ícono junto al reloj.", ToolTipIcon.Info);
                    }
                }
            };
        }

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
            chkTomar.Text = "Tomar los audios del sistema automáticamente"; chkTomar.AutoSize = true;
            chkTomar.Anchor = AnchorStyles.Left; chkTomar.Margin = new Padding(12, 0, 12, 0);
            chkTomar.Checked = !Config.Pausado;
            chkTomar.CheckedChanged += (s, e) => Pausar(!chkTomar.Checked);

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
            var menu = new ContextMenuStrip { Font = Estilo.Fuente };
            miInicio.Checked = Programa.IniciaConWindows();
            miInicio.Click += (s, e) => { miInicio.Checked = !miInicio.Checked; Programa.IniciarConWindows(miInicio.Checked); };
            menu.Items.Add(miInicio);
            menu.Items.Add("Cargar audio…", null, (s, e) => CargarAudio());
            menu.Items.Add("Volver a cargar la pantalla", null, async (s, e) => { urlCargada = null; await Entrar(); });
            menu.Items.Add("Escribir la dirección del Servidor…", null, (s, e) => DireccionAMano());
            menu.Items.Add("Ver registro de envíos", null, (s, e) => Abrir(Registro.Archivo));
            var miAuto = new ToolStripMenuItem("Volver a leer la autocorrección de Word");
            miAuto.Click += (s, e) =>
            {
                EnviarAutocorreccion(true);
                MostrarAviso("Autocorrección de Word", Autocorreccion.Error != "" ? Autocorreccion.Error
                       : Autocorreccion.Entradas.Count + " entradas con formato leídas del Normal.dotm de esta PC.");
            };
            menu.Items.Add(miAuto);
            menu.Opening += (s, e) =>
            {
                miAuto.ToolTipText = Autocorreccion.Error != "" ? Autocorreccion.Error
                    : Autocorreccion.Entradas.Count + " entradas con formato del Normal.dotm de esta PC";
            };
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Desconectar esta PC del Servidor…", null, (s, e) => Desvincular());
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
            barra.Controls.Add(chkTomar, 4, 0);
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

        // ------------------------------------------------------------ conexión
        Task ConsultarEstado() { return ConsultarEstado(false); }

        // forzar: probar ya aunque haya otra consulta esperando respuesta (p. ej. de la dirección anterior)
        async Task ConsultarEstado(bool forzar)
        {
            if (consultando > 0 && !forzar) return;
            consultando++;
            try
            {
                string probada = Config.Url;
                Respuesta r = string.IsNullOrEmpty(probada) ? null : await Servidor.Estado(probada);
                if (probada != Config.Url) return;      // la dirección se cambió a mano mientras tanto
                if (r != null && r.Codigo == 401) { PedirVincularDeNuevo(); return; }
                if (r == null || !r.Ok)
                {   // ¿cambió la dirección del túnel? (el Servidor se reinició)
                    if (estado != Conexion.SinConexion) PonerEstado(Conexion.Buscando, null);
                    string nueva = await Servidor.BuscarDireccion();
                    if (probada != Config.Url) return;
                    if (nueva != null && nueva != Config.Url)
                    {
                        var r2 = await Servidor.Estado(nueva);
                        if (probada != Config.Url) return;
                        if (r2.Ok)
                        {
                            Registro.Escribir("Nueva dirección del Servidor: " + nueva);
                            Config.Url = nueva; Config.Guardar(); r = r2;
                        }
                    }
                }
                if (r != null && r.Ok)
                {
                    bool ia = r.Datos.ContainsKey("ia") && r.Datos["ia"] is bool && (bool)r.Datos["ia"];
                    PonerEstado(ia ? Conexion.Conectado : Conexion.IaNoLista, r);
                    RevisarListos(r);
                    cola.Despertar();
                    var app = r.Datos.ContainsKey("app") ? r.Datos["app"] as Dictionary<string, object> : null;
                    if (app != null && app.ContainsKey("huella"))
                    {   // ¿hay una versión nueva de esta aplicación en el Servidor? (se baja en segundo plano)
                        Actualizador.Revisar(Config.Url, app["huella"] + "", app.ContainsKey("version") ? app["version"] + "" : "").ContinueWith(_ => { });
                    }
                    Actualizador.EnviarAvisos(Config.Url).ContinueWith(_ => { });
                    if (urlCargada != Config.Url) await Entrar();
                }
                else
                {
                    PonerEstado(Conexion.SinConexion, null);
                    if (!webLista && !webFalla) cartel.Text = "No hay conexión con el Servidor.\nPuede estar apagado o sin internet en este momento.\nSe vuelve a intentar solo cada 10 segundos; no hace falta hacer nada.";
                }
            }
            catch (Exception ex) { Registro.Escribir("Error consultando estado: " + ex.Message); }
            finally { consultando--; }
        }

        // Notificación de Windows cuando un audio de esta PC queda listo para revisar.
        void RevisarListos(Respuesta r)
        {
            object o;
            if (!r.Datos.TryGetValue("casos", out o)) return;
            var lista = o as System.Collections.IEnumerable;
            if (lista == null || o is string) return;
            foreach (var x in lista)
            {
                var c = x as Dictionary<string, object>;
                if (c == null) continue;
                string nombre = c["nombre"] + "", est = c["estado"] + "";
                string titulo = c.ContainsKey("titulo") ? c["titulo"] + "" : nombre;
                string antes;
                estadosCasos.TryGetValue(nombre, out antes);
                estadosCasos[nombre] = est;
                if (!primeraLectura && est == "listo" && antes != "listo")
                {
                    string marcas = c.ContainsKey("marcas") && c["marcas"] != null ? c["marcas"] + " marcas para revisar" : "Listo para revisar";
                    bandeja.ShowBalloonTip(8000, "Listo: " + titulo, marcas, ToolTipIcon.Info);
                    MostrarAviso("Listo para revisar: " + titulo, marcas);
                }
            }
            primeraLectura = false;
        }

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
                }
            };
            c.NavigationCompleted += (s, e) =>
            {
                if (e.IsSuccess) { web.Visible = true; cartel.Visible = false; webLista = true; }
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

        async Task Entrar()
        {
            if (string.IsNullOrEmpty(Config.Url)) return;
            var r = await Servidor.Sesion(Config.Url);
            if (r.Codigo == 401) { PedirVincularDeNuevo(); return; }
            if (!r.Ok) { Registro.Escribir("No pude abrir la sesión: " + r.Error); return; }
            string destino = Config.Url + "/entrar?codigo=" + Uri.EscapeDataString(r.Texto("codigo"));
            urlCargada = Config.Url;
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
                bandeja.ShowBalloonTip(5000, titulo, texto, ToolTipIcon.Info);
        }

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
            m.Items.Add(new ToolStripSeparator());
            m.Items.Add("Salir", null, (s, e) => Salir());
            bandeja.ContextMenuStrip = m;
            bandeja.Icon = Estilo.Icono(Estilo.Ambar);
            bandeja.Text = "Transcripción";
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
            if (chkTomar.Checked == si) chkTomar.Checked = !si;
            Registro.Escribir(si ? "Toma de audios en pausa" : "Toma de audios activada");
            ActualizarBarra();
        }

        void Salir()
        {
            if (cola.Pendientes > 0 &&
                MessageBox.Show(this, "Hay audios que todavía no llegaron al Servidor. Si salís, se envían la próxima vez que abras la aplicación.\n\n¿Salir igual?",
                    "Transcripción", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
            saliendo = true;
            bandeja.Visible = false;
            vigilante.Dispose();
            Application.Exit();
        }

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
            TextoBotonActualizar();
            Registro.Escribir("Actualización: se instala la versión " + Actualizador.ListaVersion + " (" + motivo + ").");
            if (webLista && web.CoreWebView2 != null)
            {   // guardar el borrador del informe abierto antes de cerrar
                try
                {
                    var t = web.CoreWebView2.ExecuteScriptAsync("(typeof guardarBorrador==='function') && guardarBorrador()");
                    await Task.WhenAny(t, Task.Delay(1500));
                    await Task.Delay(1200);
                }
                catch { }
            }
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
            chkTomar.Visible = !compacto; btnWord.Visible = !compacto; lblDetalle.Visible = !compacto;
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

        // ------------------------------------------------------------ audios cargados desde la pantalla (1.6)
        // La pantalla le pasa a la app los audios que se arrastran o se eligen con "Cargar audio": van a la misma
        // cola cifrada que los del sistema, así que funcionan aunque no haya conexión con el Servidor (se envían
        // solos cuando vuelve). Así la pantalla no depende de que el Servidor responda para recibir un audio.
        void AnunciarApp()
        {
            try
            {
                if (web.CoreWebView2 != null)
                    web.CoreWebView2.ExecuteScriptAsync("window.ponerApp && ponerApp({version:'" + Programa.VERSION + "', cola:true})").ContinueWith(t => { });
            }
            catch (Exception ex) { Registro.Escribir("No pude avisar a la pantalla la versión: " + ex.Message); }
        }

        string TituloAudioCargado()
        {
            return estado == Conexion.SinConexion || estado == Conexion.Buscando
                ? "Audio guardado en esta PC · se envía solo cuando vuelva la conexión"
                : "Audio cargado · enviando al Servidor";
        }

        void AudioDeLaPantalla(Dictionary<string, object> d)
        {
            object v;
            string id = d.TryGetValue("id", out v) ? v + "" : "";
            string nombre = Path.GetFileName(d.TryGetValue("nombre", out v) ? v + "" : "");
            string ok = "false", msg;
            try
            {
                if (nombre == "") nombre = "audio.wav";
                byte[] datos = Convert.FromBase64String(d.TryGetValue("datos", out v) ? v + "" : "");
                if (datos.Length == 0) throw new Exception("el archivo está vacío");
                cola.Agregar(nombre, datos, Vigilante.Huella(datos));
                Registro.Escribir("Cargado desde la pantalla: " + nombre + " (" + datos.Length / 1024 + " KB)");
                MostrarAviso(TituloAudioCargado(), nombre);
                ok = "true";
                msg = estado == Conexion.SinConexion || estado == Conexion.Buscando ? "guardado" : "enviando";
            }
            catch (Exception ex)
            {
                Registro.Escribir("No pude cargar " + nombre + " desde la pantalla: " + ex.Message);
                msg = ex.Message;
            }
            EjecutarEnWeb("window.audioEnCola && audioEnCola(" + Config.Json.Serialize(id) + ", " + ok + ", " + Config.Json.Serialize(msg) + ")");
        }

        void EjecutarEnWeb(string js)
        {
            try
            {
                if (web.CoreWebView2 != null)
                    web.CoreWebView2.ExecuteScriptAsync("window.ponerCompacto && " + js).ContinueWith(t => { });
            }
            catch (Exception ex) { Registro.Escribir("No pude avisar a la pantalla: " + ex.Message); }
        }

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

        // La pantalla del Servidor avisa: {accion:"agrandar"} | {accion:"compacto"} | {accion:"tema", oscuro:true}
        void MensajeDeLaPantalla(CoreWebView2WebMessageReceivedEventArgs e)
        {
            try
            {
                if (string.IsNullOrEmpty(Config.Url) || !e.Source.StartsWith(Config.Url, StringComparison.OrdinalIgnoreCase)) return;
                var d = Config.Json.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
                object v;
                string accion = d != null && d.TryGetValue("accion", out v) ? v + "" : "";
                if (accion == "agrandar") SalirCompacto();
                else if (accion == "compacto") EntrarCompacto();
                else if (accion == "autocorreccion") EnviarAutocorreccion(false);
                else if (accion == "audio") AudioDeLaPantalla(d);
                else if (accion == "tema")
                {
                    bool oscuro = d.TryGetValue("oscuro", out v) && v is bool && (bool)v;
                    if (oscuro != Config.Oscuro) { Config.Oscuro = oscuro; GuardarConfig(); }
                    AplicarTema(oscuro);
                }
            }
            catch (Exception ex) { Registro.Escribir("Mensaje de la pantalla ilegible: " + ex.Message); }
        }

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
            lblEstado.ForeColor = cTexto; lblDetalle.ForeColor = cSuave; chkTomar.ForeColor = cTexto;
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

        // ------------------------------------------------------------ acciones
        void CargarAudio()
        {
            using (var d = new OpenFileDialog { Title = "Cargar audio", InitialDirectory = vigilante.Carpeta,
                Filter = "Audios|*.wav;*.mp3;*.m4a;*.ogg;*.flac|Todos los archivos|*.*", Multiselect = true })
            {
                if (d.ShowDialog(this) != DialogResult.OK) return;
                foreach (var f in d.FileNames)
                {
                    try
                    {
                        byte[] datos = Vigilante.LeerTodo(f);
                        cola.Agregar(Path.GetFileName(f), datos, Vigilante.Huella(datos));
                        MostrarAviso(TituloAudioCargado(), Path.GetFileName(f));
                    }
                    catch (Exception ex) { MessageBox.Show(this, "No pude leer " + Path.GetFileName(f) + ":\n" + ex.Message, "Transcripción"); }
                }
            }
        }

        async void DireccionAMano()
        {
            string url = Pedir("Dirección del Servidor", "Pegá la dirección del Servidor (termina en trycloudflare.com):", Config.Url);
            if (url == null) return;
            url = Servidor.Normalizar(url);
            if (url == "") return;
            try { await ConectarA(url); }
            catch (Exception ex) { Registro.Escribir("Error al cambiar la dirección: " + ex.Message); }
        }

        // Cambia la dirección y prueba la conexión enseguida (sin esperar los 10 s del reloj).
        async Task ConectarA(string url)
        {
            Registro.Escribir("Dirección del Servidor cambiada a mano: " + url);
            Config.Url = url; GuardarConfig(); urlCargada = null;
            PonerEstado(Conexion.Buscando, null);
            lblDetalle.Text = "probando la dirección nueva…";
            if (!webLista) cartel.Text = "Conectando con la dirección nueva…";
            MostrarAviso("Conectando…", "Probando la dirección nueva del Servidor.");
            // se prueba ya; si había otra consulta esperando a la dirección anterior, esa descarta su resultado sola
            await ConsultarEstado(true);
            if (Config.Url != url) return;
            if (estado == Conexion.Conectado || estado == Conexion.IaNoLista)
                MostrarAviso("Conectado al Servidor", "La dirección nueva funciona.");
            else if (!pidiendoVincular)
                MostrarAviso("No se pudo conectar con esa dirección",
                    "Revisá que esté bien copiada. Se sigue intentando sola cada 10 segundos.");
        }

        void Desvincular()
        {
            if (MessageBox.Show(this, "Esta PC deja de estar autorizada y vas a tener que volver a escribir la contraseña.\n\n¿Seguir?",
                "Transcripción", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            Config.Desvincular();
            PedirVincularDeNuevo(false);
        }

        void PedirVincularDeNuevo() { PedirVincularDeNuevo(true); }

        void PedirVincularDeNuevo(bool avisar)
        {
            if (pidiendoVincular) return;
            pidiendoVincular = true;
            try
            {
                relojEstado.Stop();
                if (avisar)
                {
                    Mostrar();
                    MessageBox.Show(this, "El Servidor ya no reconoce esta PC (puede que la hayan desconectado desde el Servidor).\nVolvé a conectarla con la contraseña.",
                        "Transcripción", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                Config.Desvincular();
                using (var f = new VentanaVincular())
                {
                    if (f.ShowDialog(this) != DialogResult.OK) { saliendo = true; Application.Exit(); return; }
                }
                Text = "Transcripción — " + Config.Pc;
                urlCargada = null; primeraLectura = true;
                cola.Despertar();
                relojEstado.Start();
                ConsultarEstado().ContinueWith(_ => { });
            }
            finally { pidiendoVincular = false; }
        }

        static void Abrir(string que)
        {
            try { Process.Start(new ProcessStartInfo(que) { UseShellExecute = true }); }
            catch (Exception ex) { Registro.Escribir("No pude abrir " + que + ": " + ex.Message); }
        }

        void EnPantalla(Action a)
        {
            try { if (IsHandleCreated && !IsDisposed) BeginInvoke(a); } catch { }
        }

        static string Pedir(string titulo, string texto, string valor)
        {
            using (var f = new Form { Text = titulo, Font = Estilo.Fuente, FormBorderStyle = FormBorderStyle.FixedDialog,
                StartPosition = FormStartPosition.CenterParent, MinimizeBox = false, MaximizeBox = false,
                ClientSize = new Size(480, 140), BackColor = Estilo.Panel })
            {
                var l = new Label { Text = texto, Location = new Point(16, 14), Size = new Size(448, 36) };
                var t = new TextBox { Text = valor, Location = new Point(16, 54), Width = 448 };
                var ok = new Button(); VentanaVincular.Boton(ok, "Aceptar", true); ok.Location = new Point(370, 92);
                ok.DialogResult = DialogResult.OK;
                var no = new Button(); VentanaVincular.Boton(no, "Cancelar", false); no.Location = new Point(270, 92);
                no.DialogResult = DialogResult.Cancel;
                f.Controls.AddRange(new Control[] { l, t, ok, no });
                f.AcceptButton = ok; f.CancelButton = no;
                f.Shown += (s, e) => { t.Focus(); t.SelectAll(); };
                return f.ShowDialog() == DialogResult.OK ? t.Text : null;
            }
        }
    }
}
