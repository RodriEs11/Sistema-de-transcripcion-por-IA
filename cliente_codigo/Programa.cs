// Transcripción: aplicación de escritorio para las PC del trabajo (info-01, info-02, info-03).
// Toma los audios que el sistema de gestión deja en %TEMP%, los envía al Servidor por el túnel
// (Cloudflare o Microsoft Dev Tunnels) y muestra la interfaz de revisión del Servidor dentro de la ventana.
// No se instala: es una carpeta con Transcripcion.exe. Usa .NET Framework 4.8 y WebView2 (Edge),
// que ya vienen con Windows 10/11.
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8", FrameworkDisplayName = ".NET Framework 4.8")]
[assembly: System.Reflection.AssemblyTitle("Transcripción")]
[assembly: System.Reflection.AssemblyProduct("Transcripción")]
[assembly: System.Reflection.AssemblyDescription("Envía los audios del sistema de gestión al Servidor de transcripción")]
[assembly: System.Reflection.AssemblyCompany("Rodrigo Espíndola")]
[assembly: System.Reflection.AssemblyCopyright("Creada por Rodrigo Espíndola")]
[assembly: System.Reflection.AssemblyVersion("1.30.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.30.0.0")]

namespace Transcripcion
{
    static class Programa
    {
        public const string VERSION = "1.30";
        public static EventWaitHandle SenalMostrar;
        // Con el perfil de pruebas es otra instancia: puede abrirse junto a la app de producción.
        static string NombreSenal { get { return "Transcripcion-cliente-mostrar" + Config.Perfil; } }
        static string ClaveInicio { get { return "Transcripcion" + Config.Perfil; } }

        [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr LoadLibrary(string ruta);

        [STAThread]
        static void Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--autoprueba")
            {   // la usa la versión anterior para probar esta antes de instalarla (ver Actualizador.cs)
                Environment.Exit(Actualizador.Autoprueba(args.Length > 1 ? args[1] : ""));
                return;
            }
            try { Iniciar(args); }
            catch (Exception ex)
            {   // nunca cerrarse en silencio: mostrar qué pasó y dejarlo anotado
                Registro.Escribir("ERROR al iniciar: " + ex);
                // si es una versión recién instalada que no abre, volver sola a la anterior
                if (Actualizador.VolverAtras(ex.Message, args)) return;
                try { File.WriteAllText(Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "error_al_iniciar.txt"), DateTime.Now + "\r\n" + ex, Encoding.UTF8); } catch { }
                MessageBox.Show("Transcripción no pudo abrirse:\n\n" + ex.Message + "\n\nEl detalle quedó en error_al_iniciar.txt, junto a Transcripcion.exe.",
                    "Transcripción", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        static void Iniciar(string[] args)
        {
            bool nueva;
            int ia = Array.IndexOf(args, "--actualizada");
            bool recienActualizada = ia >= 0 && ia + 1 < args.Length;
            if (recienActualizada) Actualizador.EsperarQueTermine(args[ia + 1]);
            SenalMostrar = new EventWaitHandle(false, EventResetMode.AutoReset, NombreSenal, out nueva);
            for (int i = 0; !nueva && recienActualizada && i < 30; i++)
            {   // la versión anterior todavía se está cerrando
                SenalMostrar.Dispose();
                Thread.Sleep(1000);
                SenalMostrar = new EventWaitHandle(false, EventResetMode.AutoReset, NombreSenal, out nueva);
            }
            if (!nueva)
            {   // ya está abierta: pedirle que se muestre y salir
                SenalMostrar.Set();
                return;
            }
            if (!recienActualizada && Actualizador.HayQueVolverAtras())
            {   // la última actualización se cerró antes de abrir su ventana
                SenalMostrar.Dispose();
                Registro.Escribir("Actualización: la versión nueva no terminó de abrir la vez anterior; se vuelve a la anterior.");
                if (Actualizador.VolverAtras("se cerró antes de abrir su ventana", args)) return;
                SenalMostrar = new EventWaitHandle(false, EventResetMode.AutoReset, NombreSenal, out nueva);
            }
            try { SetProcessDPIAware(); } catch { }
            // TLS 1.2 y 1.3 para hablar con el túnel
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12 | (SecurityProtocolType)12288;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.ThreadException += (s, e) => Registro.Escribir("ERROR " + e.Exception);
            AppDomain.CurrentDomain.UnhandledException += (s, e) => Registro.Escribir("ERROR " + e.ExceptionObject);
            CargarWebView2Loader();
            Config.Cargar();
            Registro.Escribir("Inicio versión " + VERSION + " en " + Environment.MachineName + (recienActualizada ? " (recién actualizada)" : ""));
            Actualizador.AlIniciar();
            Notificaciones.PrepararIdentidad();   // 1.11: antes de abrir cualquier ventana
            RefrescarIconoDeWindows();

            if (!Config.Vinculada)
            {
                using (var f = new VentanaVincular())
                    if (f.ShowDialog() != DialogResult.OK) return;
            }
            bool oculta = Array.IndexOf(args, "--oculta") >= 0;
            Application.Run(new VentanaPrincipal(oculta));
            if (Actualizador.Saliendo) Environment.Exit(0);   // que la versión nueva no tenga que esperar
        }

        // 1.10: Windows guarda en su memoria de íconos el de Transcripcion.exe y lo usa para la barra de tareas
        // (el botón anclado) y los accesos directos. Desde el cambio de ícono (1.8) la app se actualiza sola
        // reemplazando el .exe, así que la barra de tareas seguía con el ícono viejo aunque junto al reloj ya
        // estaba el nuevo (ese lo dibuja la app). Una vez por versión se le pide a Windows que lo vuelva a leer.
        [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern void SHChangeNotify(int evento, uint flags, string item1, IntPtr item2);
        [DllImport("shell32.dll", EntryPoint = "SHChangeNotify")] static extern void SHChangeNotifyId(int evento, uint flags, IntPtr item1, IntPtr item2);
        const int SHCNE_UPDATEITEM = 0x2000, SHCNE_ASSOCCHANGED = 0x08000000;
        const uint SHCNF_IDLIST = 0, SHCNF_PATHW = 5, SHCNF_FLUSHNOWAIT = 0x3000;

        // Le avisa a Windows que cambió un archivo (para que vuelva a leer su ícono o sus propiedades).
        public static void AvisarCambio(string ruta)
        {
            try { SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSHNOWAIT, ruta, IntPtr.Zero); } catch { }
        }

        static void RefrescarIconoDeWindows()
        {
            if (Config.IconoAlDia == VERSION) return;
            var hilo = new Thread(() =>
            {
                try
                {
                    int n = 0;
                    SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSHNOWAIT, Application.ExecutablePath, IntPtr.Zero);
                    foreach (string lnk in AccesosDirectos())
                    {
                        SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSHNOWAIT, lnk, IntPtr.Zero);
                        n++;
                    }
                    SHChangeNotifyId(SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSHNOWAIT, IntPtr.Zero, IntPtr.Zero);
                    try
                    {   // la herramienta de Windows que vuelve a armar la memoria de íconos del usuario
                        string ie4 = Path.Combine(Environment.SystemDirectory, "ie4uinit.exe");
                        if (File.Exists(ie4))
                            using (var p = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(ie4, "-show")
                                   { UseShellExecute = false, CreateNoWindow = true }))
                                p.WaitForExit(15000);
                    }
                    catch { }
                    Config.IconoAlDia = VERSION;
                    Config.GuardarSeguro();
                    Registro.Escribir("Ícono: se pidió a Windows que actualice el ícono de la barra de tareas (" + n + (n == 1 ? " acceso directo)." : " accesos directos)."));
                }
                catch (Exception ex) { Registro.Escribir("Ícono: no se pudo pedir a Windows que lo actualice: " + ex.Message); }
            }) { IsBackground = true };
            hilo.Start();
        }

        // Accesos directos de esta persona que abren Transcripcion.exe (anclados en la barra de tareas, escritorio, menú Inicio).
        public static List<string> AccesosDirectos()
        {
            var lista = new List<string>();
            string ad = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            var carpetas = new[] {
                Path.Combine(ad, @"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"),
                Path.Combine(ad, @"Microsoft\Internet Explorer\Quick Launch"),
                Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory),
                Environment.GetFolderPath(Environment.SpecialFolder.Programs) };
            byte[] ascii = Encoding.ASCII.GetBytes("transcripcion.exe"), uni = Encoding.Unicode.GetBytes("transcripcion.exe");
            foreach (string c in carpetas)
            {
                try
                {
                    if (string.IsNullOrEmpty(c) || !Directory.Exists(c)) continue;
                    foreach (string f in Directory.GetFiles(c, "*.lnk", SearchOption.TopDirectoryOnly))
                    {
                        try
                        {
                            var b = File.ReadAllBytes(f);
                            if (b.Length < 64 * 1024 && (Contiene(b, ascii) || Contiene(b, uni))) lista.Add(f);
                        }
                        catch { }
                    }
                }
                catch { }
            }
            return lista;
        }

        // búsqueda sin distinguir mayúsculas (solo letras ASCII), sirve para texto ASCII y UTF-16
        static bool Contiene(byte[] datos, byte[] buscado)
        {
            for (int i = 0; i + buscado.Length <= datos.Length; i++)
            {
                int j = 0;
                for (; j < buscado.Length; j++)
                {
                    byte a = datos[i + j];
                    if (a >= (byte)'A' && a <= (byte)'Z') a = (byte)(a + 32);
                    if (a != buscado[j]) break;
                }
                if (j == buscado.Length) return true;
            }
            return false;
        }

        // El cargador nativo de WebView2 depende de si Windows es de 64 o 32 bits.
        static void CargarWebView2Loader()
        {
            string cpu = (Environment.GetEnvironmentVariable("PROCESSOR_ARCHITECTURE") ?? "").ToUpperInvariant();
            string arq = cpu == "ARM64" ? "win-arm64" : (Environment.Is64BitProcess ? "win-x64" : "win-x86");
            string ruta = Path.Combine(Config.CarpetaPrograma, "runtimes", arq, "native", "WebView2Loader.dll");
            try { if (File.Exists(ruta)) LoadLibrary(ruta); }
            catch (Exception ex) { Registro.Escribir("No pude cargar WebView2Loader: " + ex.Message); }
        }

        public static void IniciarConWindows(bool si)
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true))
                {
                    if (si) k.SetValue(ClaveInicio, "\"" + Application.ExecutablePath + "\" --oculta");
                    else k.DeleteValue(ClaveInicio, false);
                }
            }
            catch (Exception ex) { Registro.Escribir("No se pudo cambiar el inicio con Windows: " + ex.Message); }
        }

        public static bool IniciaConWindows()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", false))
                    return k != null && k.GetValue(ClaveInicio) != null;
            }
            catch { return false; }
        }

        // Carpeta de los Word descargados: la que se eligió en Configuración (si todavía existe) o Descargas.
        public static string CarpetaDescargas()
        {
            try { if (Config.CarpetaWord != "" && Directory.Exists(Config.CarpetaWord)) return Config.CarpetaWord; } catch { }
            return CarpetaDescargasWindows();
        }

        public static string CarpetaDescargasWindows()
        {
            try
            {
                IntPtr p;
                if (SHGetKnownFolderPath(new Guid("374DE290-123F-4565-9164-39C4925E467B"), 0, IntPtr.Zero, out p) == 0)
                {
                    string r = Marshal.PtrToStringUni(p);
                    Marshal.FreeCoTaskMem(p);
                    if (!string.IsNullOrEmpty(r)) return r;
                }
            }
            catch { }
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
        }

        [DllImport("shell32.dll")]
        static extern int SHGetKnownFolderPath([MarshalAs(UnmanagedType.LPStruct)] Guid id, uint flags, IntPtr token, out IntPtr ruta);
    }

    // ------------------------------------------------------------------ configuración
    static class Config
    {
        public static readonly string CarpetaPrograma = Path.GetDirectoryName(Application.ExecutablePath);
        // Perfil de pruebas: cliente\perfil_pruebas.txt junto al .exe (lo crea crear_entorno_pruebas.py; nunca se
        // distribuye a las PC). Usa otra carpeta de datos (config, llave, cola, WebView2), otra instancia y otra
        // clave de inicio con Windows: así no pisa a la app de producción de la misma PC.
        public static readonly string Perfil = File.Exists(Path.Combine(CarpetaPrograma, "perfil_pruebas.txt")) ? "-pruebas" : "";
        public static readonly string Carpeta = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Transcripcion" + Perfil);
        public static string NombreVisible { get { return Perfil == "" ? "Transcripción" : "Transcripción (PRUEBAS)"; } }
        static string Archivo { get { return Path.Combine(Carpeta, "config.json"); } }

        public static string Pc = "", Url = "", Tema = "", Aviso = "https://ntfy.sh";
        public static string CodigoInicial = "";   // código de entrada que dio el Servidor al vincular (solo en memoria)
        public static bool Pausado = Perfil != "";                 // en pruebas arranca sin tomar los audios de %TEMP%
        public static bool AvisarListos = true;                    // notificación cuando un informe queda listo (1.9)
        public static bool NotificacionesWindows = false;          // globos/notificaciones de Windows; apagadas por defecto (1.14)
        public static string CarpetaWord = "";                     // carpeta elegida para los Word ("" = Descargas) (1.9)
        public static bool Compacto = false, Oscuro = false;      // modo compacto y tema (los elige la persona)
        public static string BordesCompacto = "";                  // "x,y,ancho,alto" de la ventana compacta
        public static string HuellaApp = "", HuellaFallida = "";    // versión de la app que ya está al día / que falló acá
        public static string IconoAlDia = "";                      // versión que ya le pidió a Windows refrescar el ícono (1.10)
        public static string IdentidadAlDia = "";                  // identidad de Windows ya preparada para las notificaciones (1.11)
        static readonly object cerrojoGuardar = new object();
        static string llaveCifrada = "";
        static readonly byte[] Entropia = Encoding.UTF8.GetBytes("Transcripcion-llave-v1");
        public static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };

        // .NET Framework 4.8 solo tiene TrimEnd(params char[]): se pasa el arreglo explícito
        public static readonly char[] Barra = { '/' };

        public static bool Vinculada { get { return Pc != "" && llaveCifrada != ""; } }

        // La llave se guarda cifrada con la cuenta de Windows de esta persona (DPAPI).
        public static string Llave
        {
            get
            {
                if (llaveCifrada == "") return "";
                try
                {
                    return Encoding.UTF8.GetString(ProtectedData.Unprotect(
                        Convert.FromBase64String(llaveCifrada), Entropia, DataProtectionScope.CurrentUser));
                }
                catch { return ""; }
            }
            set
            {
                llaveCifrada = string.IsNullOrEmpty(value) ? "" : Convert.ToBase64String(ProtectedData.Protect(
                    Encoding.UTF8.GetBytes(value), Entropia, DataProtectionScope.CurrentUser));
            }
        }

        public static void Cargar()
        {
            Directory.CreateDirectory(Carpeta);
            try
            {   // conexion.json viene del Servidor, junto al .exe
                string c = Path.Combine(CarpetaPrograma, "conexion.json");
                if (File.Exists(c))
                {
                    var d = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(c, Encoding.UTF8));
                    if (d.ContainsKey("tema")) Tema = d["tema"] + "";
                    if (d.ContainsKey("aviso")) Aviso = (d["aviso"] + "").TrimEnd(Barra);
                }
            }
            catch (Exception ex) { Registro.Escribir("conexion.json ilegible: " + ex.Message); }
            try
            {
                if (File.Exists(Archivo))
                {
                    var d = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(Archivo, Encoding.UTF8));
                    object v;
                    if (d.TryGetValue("pc", out v)) Pc = v + "";
                    if (d.TryGetValue("url", out v)) Url = v + "";
                    if (d.TryGetValue("llave", out v)) llaveCifrada = v + "";
                    if (d.TryGetValue("pausado", out v)) Pausado = v is bool && (bool)v;
                    if (d.TryGetValue("avisar_listos", out v)) AvisarListos = !(v is bool) || (bool)v;
                    if (d.TryGetValue("notificaciones_windows", out v)) NotificacionesWindows = v is bool && (bool)v;
                    if (d.TryGetValue("carpeta_word", out v)) CarpetaWord = v + "";
                    if (d.TryGetValue("compacto", out v)) Compacto = v is bool && (bool)v;
                    if (d.TryGetValue("oscuro", out v)) Oscuro = v is bool && (bool)v;
                    if (d.TryGetValue("bordes_compacto2", out v)) BordesCompacto = v + "";   // desde la 1.4 (la de antes era más ancha)
                    if (d.TryGetValue("app_huella", out v)) HuellaApp = v + "";
                    if (d.TryGetValue("app_huella_fallida", out v)) HuellaFallida = v + "";
                    if (d.TryGetValue("icono_al_dia", out v)) IconoAlDia = v + "";
                    if (d.TryGetValue("identidad_al_dia", out v)) IdentidadAlDia = v + "";
                    if (Tema == "" && d.TryGetValue("tema", out v)) Tema = v + "";
                }
            }
            catch (Exception ex) { Registro.Escribir("config.json ilegible: " + ex.Message); }
            if (Llave == "") llaveCifrada = "";   // copiada de otro usuario: no sirve
        }

        public static void Guardar()
        {
            lock (cerrojoGuardar)
            {
                var d = new Dictionary<string, object> {
                    { "pc", Pc }, { "url", Url }, { "llave", llaveCifrada }, { "pausado", Pausado }, { "tema", Tema }, { "avisar_listos", AvisarListos }, { "notificaciones_windows", NotificacionesWindows }, { "carpeta_word", CarpetaWord },
                    { "compacto", Compacto }, { "oscuro", Oscuro }, { "bordes_compacto2", BordesCompacto },
                    { "app_huella", HuellaApp }, { "app_huella_fallida", HuellaFallida }, { "icono_al_dia", IconoAlDia }, { "identidad_al_dia", IdentidadAlDia } };
                Directory.CreateDirectory(Carpeta);
                string tmp = Archivo + ".tmp";
                File.WriteAllText(tmp, Json.Serialize(d), Encoding.UTF8);
                if (File.Exists(Archivo)) File.Delete(Archivo);
                File.Move(tmp, Archivo);
            }
        }

        public static void GuardarSeguro()
        {
            try { Guardar(); }
            catch (Exception ex) { Registro.Escribir("No pude guardar la configuración: " + ex.Message); }
        }

        public static void Desvincular()
        {
            llaveCifrada = "";
            Guardar();
        }
    }

    // ------------------------------------------------------------------ registro
    static class Registro
    {
        static readonly object cerrojo = new object();
        public static string Archivo { get { return Path.Combine(Config.Carpeta, "registro.txt"); } }

        public static void Escribir(string texto)
        {
            try
            {
                lock (cerrojo)
                {
                    Directory.CreateDirectory(Config.Carpeta);
                    var fi = new FileInfo(Archivo);
                    if (fi.Exists && fi.Length > 1024 * 1024)
                    {
                        string viejo = Archivo + ".anterior";
                        if (File.Exists(viejo)) File.Delete(viejo);
                        File.Move(Archivo, viejo);
                    }
                    File.AppendAllText(Archivo, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + texto + Environment.NewLine, Encoding.UTF8);
                }
            }
            catch { }
        }
    }
}
