// Toma de audios de %TEMP% y cola de envío al Servidor.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Transcripcion
{
    // Vigila la carpeta temporal. Cuando aparece un .wav espera a que el sistema de gestión termine de
    // escribirlo, lo lee SIN bloquearlo (el sistema puede seguir usándolo y borrarlo) y lo entrega.
    class Vigilante : IDisposable
    {
        class Candidato { public long Tam = -1; public DateTime Visto, UltimoCambio; }

        public readonly string Carpeta = Path.GetTempPath();
        readonly ConcurrentDictionary<string, Candidato> candidatos = new ConcurrentDictionary<string, Candidato>(StringComparer.OrdinalIgnoreCase);
        readonly HashSet<string> vistas = new HashSet<string>();      // huellas ya entregadas
        readonly string archivoVistas = Path.Combine(Config.Carpeta, "huellas_enviadas.txt");
        FileSystemWatcher w;
        System.Threading.Timer reloj;
        int revisando = 0;

        public event Action<string, byte[], string> AudioListo;     // nombre, contenido, huella
        public const long MinimoBytes = 8 * 1024;

        public void Iniciar()
        {
            try { foreach (var l in File.ReadAllLines(archivoVistas)) if (l.Trim() != "") vistas.Add(l.Trim()); } catch { }
            w = new FileSystemWatcher(Carpeta, "*.wav") { IncludeSubdirectories = true, InternalBufferSize = 64 * 1024,
                NotifyFilter = NotifyFilters.FileName | NotifyFilters.Size | NotifyFilters.LastWrite };
            w.Created += (s, e) => Anotar(e.FullPath);
            w.Changed += (s, e) => Anotar(e.FullPath);
            w.Renamed += (s, e) => Anotar(e.FullPath);
            w.Error += (s, e) => { Registro.Escribir("Se perdieron avisos de la carpeta temporal; reviso de nuevo"); Barrer(TimeSpan.FromMinutes(3)); };
            w.EnableRaisingEvents = true;
            reloj = new System.Threading.Timer(_ => Revisar(), null, 700, 700);
            Barrer(TimeSpan.FromMinutes(20));   // audios abiertos un rato antes de abrir la aplicación
            Registro.Escribir("Vigilando " + Carpeta);
        }

        void Barrer(TimeSpan reciente)
        {
            try
            {
                foreach (var f in Directory.EnumerateFiles(Carpeta, "*.wav", SearchOption.AllDirectories))
                    try { if (DateTime.Now - File.GetLastWriteTime(f) < reciente) Anotar(f); } catch { }
            }
            catch { }
        }

        void Anotar(string ruta)
        {
            if (Config.Pausado) return;
            if (!ruta.EndsWith(".wav", StringComparison.OrdinalIgnoreCase)) return;
            var ahora = DateTime.Now;
            candidatos.TryAdd(ruta, new Candidato { Visto = ahora, UltimoCambio = ahora });
        }

        void Revisar()
        {
            if (Interlocked.Exchange(ref revisando, 1) == 1) return;
            try
            {
                foreach (var par in candidatos.ToArray())
                {
                    string ruta = par.Key; var c = par.Value; var ahora = DateTime.Now;
                    Candidato quitar;
                    try
                    {
                        var fi = new FileInfo(ruta);
                        if (!fi.Exists) { candidatos.TryRemove(ruta, out quitar); continue; }
                        if (fi.Length != c.Tam) { c.Tam = fi.Length; c.UltimoCambio = ahora; continue; }
                        if ((ahora - c.UltimoCambio).TotalSeconds < 1.2) continue;          // todavía se escribe
                        if (fi.Length < MinimoBytes) { candidatos.TryRemove(ruta, out quitar); continue; }
                        byte[] cab = LeerInicio(ruta, 12);
                        bool esWav = cab.Length == 12 && Encoding.ASCII.GetString(cab, 0, 4) == "RIFF" && Encoding.ASCII.GetString(cab, 8, 4) == "WAVE";
                        if (!esWav)
                        {
                            if ((ahora - c.Visto).TotalSeconds > 20) candidatos.TryRemove(ruta, out quitar);
                            continue;
                        }
                        uint riff = BitConverter.ToUInt32(cab, 4);
                        bool completo = riff == 0 || riff == 0xFFFFFFFF || (long)riff + 8 <= fi.Length;
                        if (!completo && (ahora - c.Visto).TotalSeconds < 20) continue;     // falta la cabecera final
                        byte[] datos = LeerTodo(ruta);
                        candidatos.TryRemove(ruta, out quitar);
                        string huella = Huella(datos);
                        lock (vistas)
                        {
                            if (vistas.Contains(huella)) continue;      // el mismo audio abierto otra vez
                            vistas.Add(huella);
                            try { File.AppendAllText(archivoVistas, huella + Environment.NewLine); } catch { }
                        }
                        Registro.Escribir("Audio tomado: " + Path.GetFileName(ruta) + " (" + (datos.Length / 1024) + " KB)");
                        var h = AudioListo; if (h != null) h(Path.GetFileName(ruta), datos, huella);
                    }
                    catch (IOException ex)
                    {   // el sistema lo tiene abierto sin permitir lectura: reintentar un minuto
                        if ((ahora - c.Visto).TotalSeconds > 60)
                        {
                            candidatos.TryRemove(ruta, out quitar);
                            Registro.Escribir("No pude leer " + Path.GetFileName(ruta) + ": " + ex.Message);
                        }
                    }
                    catch (UnauthorizedAccessException) { candidatos.TryRemove(ruta, out quitar); }
                }
            }
            finally { Interlocked.Exchange(ref revisando, 0); }
        }

        static FileStream AbrirCompartido(string ruta)
        {
            return new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        }

        static byte[] LeerInicio(string ruta, int n)
        {
            using (var fs = AbrirCompartido(ruta))
            {
                var b = new byte[n]; int leidos = 0, r;
                while (leidos < n && (r = fs.Read(b, leidos, n - leidos)) > 0) leidos += r;
                if (leidos < n) Array.Resize(ref b, leidos);
                return b;
            }
        }

        public static byte[] LeerTodo(string ruta)
        {
            using (var fs = AbrirCompartido(ruta))
            using (var ms = new MemoryStream())
            {
                fs.CopyTo(ms);
                return ms.ToArray();
            }
        }

        public static string Huella(byte[] datos)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(datos)).Replace("-", "").ToLowerInvariant();
        }

        public void Dispose()
        {
            if (w != null) w.Dispose();
            if (reloj != null) reloj.Dispose();
        }
    }

    // Cola de envío. Cada audio se guarda primero CIFRADO en esta PC (por si se corta internet) y se
    // borra apenas el Servidor confirma que lo recibió.
    class ColaEnvio
    {
        readonly string carpeta = Path.Combine(Config.Carpeta, "pendientes");
        readonly SemaphoreSlim despertar = new SemaphoreSlim(0);
        static readonly byte[] Entropia = Encoding.UTF8.GetBytes("Transcripcion-audio-v1");

        public event Action<string, string, bool> Enviado;      // nombre original, nombre del caso, duplicado
        public event Action<string, string> Rechazado;         // nombre original, motivo
        public event Action LlaveInvalida;
        public event Action<int> PendientesCambio;

        public ColaEnvio() { Directory.CreateDirectory(carpeta); }

        public int Pendientes { get { try { return Directory.GetFiles(carpeta, "*.audio").Length; } catch { return 0; } } }

        public void Agregar(string nombre, byte[] datos, string huella)
        {
            string id = DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + "_" + huella.Substring(0, 12);
            File.WriteAllBytes(Path.Combine(carpeta, id + ".audio"),
                ProtectedData.Protect(datos, Entropia, DataProtectionScope.CurrentUser));
            File.WriteAllText(Path.Combine(carpeta, id + ".nombre"), nombre, Encoding.UTF8);
            Avisar();
            Despertar();
        }

        public void Despertar() { if (despertar.CurrentCount == 0) despertar.Release(); }

        void Avisar() { var h = PendientesCambio; if (h != null) h(Pendientes); }

        public void Iniciar() { Task.Run(() => Bucle()); }

        async Task Bucle()
        {
            while (true)
            {
                bool todoBien = true;
                foreach (var f in Directory.GetFiles(carpeta, "*.audio").OrderBy(x => x))
                {
                    string id = Path.GetFileNameWithoutExtension(f);
                    string fNombre = Path.Combine(carpeta, id + ".nombre");
                    string nombre = File.Exists(fNombre) ? File.ReadAllText(fNombre, Encoding.UTF8) : "audio.wav";
                    byte[] datos;
                    try { datos = ProtectedData.Unprotect(File.ReadAllBytes(f), Entropia, DataProtectionScope.CurrentUser); }
                    catch (Exception ex) { Registro.Escribir("Pendiente ilegible, se descarta: " + ex.Message); Borrar(f, fNombre); continue; }
                    if (string.IsNullOrEmpty(Config.Url)) { todoBien = false; break; }
                    var r = await Servidor.SubirAudio(Config.Url, nombre, datos, Vigilante.Huella(datos));
                    if (r.Ok)
                    {
                        Borrar(f, fNombre);
                        bool dup = r.Datos.ContainsKey("duplicado") && r.Datos["duplicado"] is bool && (bool)r.Datos["duplicado"];
                        Registro.Escribir("Enviado " + nombre + " → " + r.Texto("nombre") + (dup ? " (ya estaba)" : ""));
                        var h = Enviado; if (h != null) h(nombre, r.Texto("nombre"), dup);
                    }
                    else if (r.Codigo == 401)
                    {
                        todoBien = false; var h = LlaveInvalida; if (h != null) h(); break;
                    }
                    else if (r.Codigo == 400 || r.Codigo == 413 || (r.Codigo == 422 && !(r.Error ?? "").Contains("dañado")))
                    {   // el Servidor no lo acepta: no tiene sentido reintentar
                        Borrar(f, fNombre);
                        Registro.Escribir("Rechazado " + nombre + ": " + r.Error);
                        var h = Rechazado; if (h != null) h(nombre, r.Error);
                    }
                    else { todoBien = false; Registro.Escribir("No se pudo enviar " + nombre + ": " + r.Error); break; }
                    Avisar();
                }
                Avisar();
                await despertar.WaitAsync(todoBien ? 60000 : 15000);
            }
        }

        static void Borrar(params string[] fs) { foreach (var f in fs) try { File.Delete(f); } catch { } }
    }
}
