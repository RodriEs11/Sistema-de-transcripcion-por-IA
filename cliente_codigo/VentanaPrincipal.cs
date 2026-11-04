// Ventana principal: barra de estado propia + la interfaz del Servidor (WebView2) + ícono junto al reloj.
// Modo compacto: ventana chica, siempre visible al costado, que muestra solo la cola y los avisos;
// al hacer clic en un caso (o en "Agrandar") vuelve al tamaño normal y lo abre.
//
// La clase está partida por responsabilidad (partial class): acá van los campos, el arranque oculto y el
// constructor; el resto, en VentanaPrincipal.<Parte>.cs: Barra, Conexion, Web, Puente (mensajes con la página),
// Aviso, Bandeja, Actualizacion, Compacto, Audios, Autocorreccion, Tema, Configuracion y Acciones.
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
    enum Conexion { Iniciando, Conectado, IaNoLista, Buscando, SinConexion }

    partial class VentanaPrincipal : Form
    {
        readonly WebView2 web = new WebView2();
        readonly Label cartel = new Label();
        readonly Button btnEdge = new Button(), btnReintentar = new Button();
        readonly Panel punto = new Panel();
        readonly Label lblEstado = new Label(), lblDetalle = new Label();
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
        bool yaEntro = false;      // la pantalla ya se abrió una vez en esta ejecución: las siguientes son reconexiones
        // 1.11: la pantalla del Servidor no cargó (error de Cloudflare o sin conexión): se muestra el cartel propio
        bool webCaida = false;
        string navActual = null;                  // dirección de la página que se está abriendo
        DateTime descargaDesde = DateTime.MinValue;
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
            Text = Config.NombreVisible + " — " + Config.Pc;
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
            VentanaVincular.Boton(btnReintentar, "Reintentar ahora", true);
            btnReintentar.Visible = false; btnReintentar.Anchor = AnchorStyles.None;
            btnReintentar.Click += async (s, e) => await Reintentar();
            cartel.Controls.Add(btnReintentar);
            cartel.Resize += (s, e) => UbicarBotonesCartel();
            cartel.TextChanged += (s, e) => UbicarBotonesCartel();

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
                catch (Exception ex) {
                    Registro.Escribir("No pude guardar " + nombre + ": " + ex.Message);
                    EnPantalla(() => MostrarAviso("No se pudo conservar el audio", "No cierres el audio original. Se reintentará automáticamente."));
                    return false;
                }
                try { EnPantalla(() => MostrarAviso("Audio nuevo tomado del sistema",
                    nombre + " · " + (datos.Length / 1024.0 / 1024.0).ToString("0.0") + " MB · enviando al Servidor…")); }
                catch (Exception ex) { Registro.Escribir("Audio conservado; no se pudo mostrar el aviso: " + ex.Message); }
                return true;
            };
            cola.Enviado += (nombre, caso, dup) => EnPantalla(() =>
            {
                MostrarAviso(dup ? "Este audio ya estaba en el Servidor" : "Audio enviado al Servidor",
                    nombre + (dup ? " · se abre el caso que ya existía" : " · transcribiendo… te aviso cuando esté listo"));
                ActualizarBarra();
            });
            cola.Rechazado += (nombre, motivo) => EnPantalla(() => MostrarAviso(nombre, motivo));
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
                {   // cerrar = esconder; sigue tomando audios y la sesión del transcriptor sigue abierta (al volver a
                    // abrirla no se piden de nuevo usuario y contraseña). Para cambiar de persona: «Cerrar sesión».
                    e.Cancel = true; Hide();
                    if (!avisoBandejaMostrado)
                    {
                        avisoBandejaMostrado = true;
                        Notificaciones.Globo(bandeja, 5000, Config.NombreVisible + " sigue funcionando",
                            "Los audios se siguen enviando. Para abrirla, hacé doble clic en el ícono junto al reloj.");
                    }
                }
            };
        }
    }
}
