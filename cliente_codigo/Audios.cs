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
        class Candidato { public long Tam = -1; public DateTime Visto, UltimoCambio, Reintentar; }

        public readonly string Carpeta = Path.GetTempPath();
        readonly ConcurrentDictionary<string, Candidato> candidatos = new ConcurrentDictionary<string, Candidato>(StringComparer.OrdinalIgnoreCase);
        readonly HashSet<string> vistas = new HashSet<string>();      // huellas ya entregadas
        readonly string archivoVistas = Path.Combine(Config.Carpeta, "huellas_enviadas.txt");
        FileSystemWatcher w;
        System.Threading.Timer reloj;
        int revisando = 0;

        public event Func<string, byte[], string, bool> AudioListo; // true solo si quedó persistido
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
                    if (ahora < c.Reintentar) continue;
                    Candidato quitar;
                    try
                    {
                        var fi = new FileInfo(ruta);
                        // Exists también devuelve false ante algunos errores de permisos. Length los informa.
                        long longitud = fi.Length;
                        if (longitud != c.Tam) { c.Tam = longitud; c.UltimoCambio = ahora; continue; }
                        if ((ahora - c.UltimoCambio).TotalSeconds < 1.2) continue;          // todavía se escribe
                        if (longitud < MinimoBytes) { candidatos.TryRemove(ruta, out quitar); continue; }
                        byte[] cab = LeerInicio(ruta, 12);
                        bool esWav = cab.Length == 12 && Encoding.ASCII.GetString(cab, 0, 4) == "RIFF" && Encoding.ASCII.GetString(cab, 8, 4) == "WAVE";
                        if (!esWav)
                        {
                            if ((ahora - c.Visto).TotalSeconds > 20) candidatos.TryRemove(ruta, out quitar);
                            continue;
                        }
                        uint riff = BitConverter.ToUInt32(cab, 4);
                        bool completo = riff == 0 || riff == 0xFFFFFFFF || (long)riff + 8 <= longitud;
                        if (!completo) { c.Reintentar = ahora.AddSeconds(10); continue; } // el tiempo no vuelve completo un WAV truncado
                        byte[] datos = LeerTodo(ruta);
                        uint largoLeido = datos.Length >= 12 ? BitConverter.ToUInt32(datos, 4) : 0;
                        if (datos.Length != longitud || datos.Length < MinimoBytes
                            || Encoding.ASCII.GetString(datos, 0, 4) != "RIFF" || Encoding.ASCII.GetString(datos, 8, 4) != "WAVE"
                            || (largoLeido != 0 && largoLeido != uint.MaxValue && (long)largoLeido + 8 > datos.Length))
                        { c.Reintentar = ahora.AddSeconds(10); continue; }
                        string huella = Huella(datos);
                        lock (vistas)
                        {
                            if (vistas.Contains(huella)) { candidatos.TryRemove(ruta, out quitar); continue; }
                        }
                        var h = AudioListo;
                        bool guardado = false;
                        try { guardado = h != null && h(Path.GetFileName(ruta), datos, huella); }
                        catch (Exception ex) { Registro.Escribir("No se pudo conservar el audio; se reintentará: " + ex.Message); }
                        if (!guardado) { c.Reintentar = ahora.AddSeconds(10); continue; }
                        lock (vistas)
                        {
                            vistas.Add(huella);
                            try { GuardarHuellas(); }
                            catch (Exception ex) { Registro.Escribir("Audio en cola, pero no se pudo guardar su huella: " + ex.Message); }
                        }
                        candidatos.TryRemove(ruta, out quitar);
                        Registro.Escribir("Audio tomado: " + Path.GetFileName(ruta) + " (" + (datos.Length / 1024) + " KB)");
                    }
                    catch (FileNotFoundException) { candidatos.TryRemove(ruta, out quitar); }
                    catch (DirectoryNotFoundException) { candidatos.TryRemove(ruta, out quitar); }
                    catch (IOException ex)
                    {   // Puede seguir abierto por el grabador: el tiempo no demuestra que se haya perdido.
                        c.Reintentar = ahora.AddSeconds(10);
                        Registro.Escribir("No pude leer " + Path.GetFileName(ruta) + "; se reintentará: " + ex.Message);
                    }
                    catch (UnauthorizedAccessException ex)
                    {
                        c.Reintentar = ahora.AddSeconds(10);
                        Registro.Escribir("Sin permiso para leer el audio; se reintentará: " + ex.Message);
                    }
                }
            }
            finally { Interlocked.Exchange(ref revisando, 0); }
        }

        static FileStream AbrirCompartido(string ruta)
        {
            return new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        }

        void GuardarHuellas()
        {
            string temporal = archivoVistas + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                using (var f = new FileStream(temporal, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    byte[] datos = Encoding.UTF8.GetBytes(string.Join(Environment.NewLine, vistas) + Environment.NewLine);
                    f.Write(datos, 0, datos.Length); f.Flush(true);
                }
                if (File.Exists(archivoVistas)) File.Replace(temporal, archivoVistas, null);
                else File.Move(temporal, archivoVistas);
            }
            finally { try { if (File.Exists(temporal)) File.Delete(temporal); } catch (IOException) { } }
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
        readonly object publicando = new object();
        static readonly byte[] Entropia = Encoding.UTF8.GetBytes("Transcripcion-audio-v1");

        public event Action<string, string, bool> Enviado;      // nombre original, nombre del caso, duplicado
        public event Action<string, string> Rechazado;         // nombre original, motivo
        public event Action LlaveInvalida;
        public event Action<int> PendientesCambio;

        public ColaEnvio() { Directory.CreateDirectory(carpeta); }

        public int Pendientes { get { try { return Directory.GetFiles(carpeta, "*.audio").Length; } catch { return 0; } } }

        public void Agregar(string nombre, byte[] datos, string huella)
        {
          lock (publicando)
          {
            string id = DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + "_" + Guid.NewGuid().ToString("N");
            string destino = Path.Combine(carpeta, id + ".audio");
            // El lector solo ve *.audio. Publicar el audio es el último paso, con nombre ya cerrado.
            EscribirDuradero(Path.Combine(carpeta, id + ".nombre"), Encoding.UTF8.GetBytes(nombre));
            EscribirDuradero(destino + ".pendiente", ProtectedData.Protect(datos, Entropia, DataProtectionScope.CurrentUser));
            File.Move(destino + ".pendiente", destino);
          }
            // Una notificación que falla no debe convertir un audio ya persistido en fallo de captura.
            try { Avisar(); } catch (Exception ex) { Registro.Escribir("Audio conservado; falló el aviso: " + ex.Message); }
            Despertar();
        }

        static void EscribirDuradero(string ruta, byte[] datos)
        {
            using (var f = new FileStream(ruta, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { f.Write(datos, 0, datos.Length); f.Flush(true); }
        }

        void ConservarParaRecuperar(string audio, string nombre, string motivo)
        {
            string destino = Path.Combine(carpeta, "recuperacion");
            Directory.CreateDirectory(destino);
            // No borrar si el traslado falla: el bucle reintentará conservando el original.
            File.Move(audio, Path.Combine(destino, Path.GetFileName(audio) + "." + Guid.NewGuid().ToString("N")));
            if (File.Exists(nombre))
                try { File.Move(nombre, Path.Combine(destino, Path.GetFileName(nombre))); } catch (IOException) { }
            Registro.Escribir("Audio conservado en recuperación: " + motivo);
            var h = Rechazado; if (h != null) h("Audio conservado para recuperación", motivo);
        }

        void RecuperarInterrumpidos()
        {
          lock (publicando)
          {
            foreach (string f in Directory.GetFiles(carpeta, "*.audio.pendiente"))
            {
                string destino = f.Substring(0, f.Length - ".pendiente".Length);
                string nombre = Path.ChangeExtension(destino, ".nombre");
                try
                {
                    ProtectedData.Unprotect(File.ReadAllBytes(f), Entropia, DataProtectionScope.CurrentUser);
                    if (!File.Exists(nombre)) throw new CryptographicException("Falta el nombre del audio interrumpido.");
                    File.Move(f, destino);
                }
                catch (CryptographicException) { ConservarParaRecuperar(f, nombre, "La escritura quedó incompleta. Se conserva para revisión."); }
                catch (IOException ex) { Registro.Escribir("Pendiente conservado; no se pudo recuperar: " + ex.Message); }
                catch (UnauthorizedAccessException ex) { Registro.Escribir("Pendiente conservado; no hay permiso: " + ex.Message); }
            }
          }
        }

        public void Despertar() { if (despertar.CurrentCount == 0) despertar.Release(); }

        static bool Confirmado(Respuesta r)
        {
            object ok, nombre, error;
            return r != null && r.Ok && r.Datos != null
                && r.Datos.TryGetValue("ok", out ok) && ok is bool && (bool)ok
                && r.Datos.TryGetValue("nombre", out nombre) && nombre is string && !string.IsNullOrWhiteSpace((string)nombre)
                && !r.Datos.TryGetValue("error", out error);
        }

        void Avisar() { var h = PendientesCambio; if (h != null) h(Pendientes); }

        public void Iniciar() { Task.Run(() => Bucle()); }

        async Task Bucle()
        {
            try { RecuperarInterrumpidos(); }
            catch (Exception ex) { Registro.Escribir("No se pudo completar la recuperación de audios: " + ex.Message); }
            while (true)
            {
              bool falloCiclo = false;
              try
              {
                bool todoBien = true;
                foreach (var f in Directory.GetFiles(carpeta, "*.audio").OrderBy(x => x))
                {
                    string id = Path.GetFileNameWithoutExtension(f);
                    string fNombre = Path.Combine(carpeta, id + ".nombre");
                    string nombre = File.Exists(fNombre) ? File.ReadAllText(fNombre, Encoding.UTF8) : "audio.wav";
                    byte[] datos;
                    try { datos = ProtectedData.Unprotect(File.ReadAllBytes(f), Entropia, DataProtectionScope.CurrentUser); }
                    catch (CryptographicException)
                    { ConservarParaRecuperar(f, fNombre, "No se pudo descifrar. El audio no fue borrado."); Avisar(); continue; }
                    catch (IOException ex) { Registro.Escribir("No se pudo leer el pendiente; se reintentará: " + ex.Message); todoBien = false; continue; }
                    catch (UnauthorizedAccessException ex) { Registro.Escribir("Sin permiso para leer el pendiente; se reintentará: " + ex.Message); todoBien = false; continue; }
                    if (string.IsNullOrEmpty(Config.Url)) { todoBien = false; break; }
                    var r = await Servidor.SubirAudio(Config.Url, nombre, datos, Vigilante.Huella(datos));
                    if (Confirmado(r))
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
                        ConservarParaRecuperar(f, fNombre, r.Error ?? "El servidor rechazó el audio.");
                        Registro.Escribir("Rechazado " + nombre + ": " + r.Error);
                    }
                    else { todoBien = false; Registro.Escribir("No se pudo enviar " + nombre + ": " + (r.Error ?? "El servidor no confirmó la recepción del audio.")); break; }
                    Avisar();
                }
                Avisar();
                await despertar.WaitAsync(todoBien ? 60000 : 15000);
              }
              catch (Exception ex)
              {
                  Registro.Escribir("La cola conserva los audios y volverá a intentar: " + ex.Message);
                  falloCiclo = true;
              }
              if (falloCiclo) await Task.Delay(15000);
            }
        }

        static void Borrar(params string[] fs) { foreach (var f in fs) try { File.Delete(f); } catch { } }
    }
}
