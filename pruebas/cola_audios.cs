// Compilar junto con cliente_codigo/Audios.cs. Stubs: nunca usa la configuración ni la red reales.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Collections.Generic;
namespace Transcripcion
{
    static class Config { public static string Carpeta; public static bool Pausado = false; public static string Url = ""; }
    static class Registro { public static void Escribir(string s) { } }
    class Respuesta { public bool Ok = false; public int Codigo = 400; public string Error = "Rechazo ficticio"; public Dictionary<string, object> Datos = new Dictionary<string, object>(); public string Texto(string c) { return "ficticio"; } }
    static class Servidor {
        public static Respuesta Siguiente = new Respuesta();
        public static Task<Respuesta> SubirAudio(string u, string n, byte[] d, string h) { return Task.FromResult(Siguiente); }
    }
    static class PruebaCola
    {
        static void Exigir(bool v, string m) { if (!v) throw new Exception(m); }
        static object Invocar(object o, string m, params object[] a)
        { return o.GetType().GetMethod(m, BindingFlags.NonPublic | BindingFlags.Instance).Invoke(o, a); }
        static readonly byte[] Datos = Encoding.UTF8.GetBytes("Audio ficticio para probar persistencia");
        static readonly byte[] Entropia = Encoding.UTF8.GetBytes("Transcripcion-audio-v1");
        static int Main(string[] args)
        {
            try
            {
                Config.Carpeta = Path.GetFullPath(args[0]); Directory.CreateDirectory(Config.Carpeta);
                var c = new ColaEnvio(); string p = Path.Combine(Config.Carpeta, "pendientes");
                // Publicación concurrente con nombres únicos y formato cifrado v1 compatible.
                Parallel.For(0, 12, i => c.Agregar("ficticio.wav", Datos, Vigilante.Huella(Datos)));
                Exigir(c.Pendientes == 12, "Colisión de nombres o pérdida");
                foreach (string f in Directory.GetFiles(p, "*.audio"))
                {
                    Exigir(File.Exists(Path.ChangeExtension(f, ".nombre")), "Audio publicado sin metadatos");
                    Exigir(ProtectedData.Unprotect(File.ReadAllBytes(f), Entropia, DataProtectionScope.CurrentUser).SequenceEqual(Datos), "Contenido distinto");
                }
                Exigir(Directory.GetFiles(p, "*.pendiente").Length == 0, "Temporal publicado incorrectamente");
                // Fallo de observador no invalida la persistencia ya realizada.
                c.PendientesCambio += n => { throw new Exception("Aviso ficticio fallido"); };
                c.Agregar("aviso.wav", Datos, Vigilante.Huella(Datos));
                Exigir(c.Pendientes == 13, "Fallo de aviso afectó audio");
                string interrumpido = Path.Combine(p, "interrumpido.audio.pendiente");
                File.WriteAllBytes(interrumpido, ProtectedData.Protect(Datos, Entropia, DataProtectionScope.CurrentUser));
                File.WriteAllText(Path.Combine(p, "interrumpido.nombre"), "ficticio.wav");
                string roto = Path.Combine(p, "roto.audio.pendiente"); File.WriteAllBytes(roto, new byte[] { 1, 2, 3 });
                Invocar(c, "RecuperarInterrumpidos");
                Exigir(File.Exists(Path.Combine(p, "interrumpido.audio")), "No recuperó escritura completa");
                Exigir(!File.Exists(roto) && Directory.GetFiles(Path.Combine(p, "recuperacion"), "roto*").Length == 1, "Destruyó temporal incompleto");
                // Captura fallida no confirma huella y conserva candidato para reintento.
                string wav = Path.Combine(Config.Carpeta, "ficticio.wav"); var b = new byte[9000];
                Encoding.ASCII.GetBytes("RIFF").CopyTo(b, 0); Encoding.ASCII.GetBytes("WAVE").CopyTo(b, 8); File.WriteAllBytes(wav, b);
                var v = new Vigilante(); bool aceptar = false; int intentos = 0;
                v.AudioListo += (n, d, h) => { intentos++; return aceptar; };
                Invocar(v, "Anotar", wav); Invocar(v, "Revisar");
                var candidatos = v.GetType().GetField("candidatos", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(v);
                object candidato = candidatos.GetType().GetProperty("Item").GetValue(candidatos, new object[] { wav });
                candidato.GetType().GetField("UltimoCambio").SetValue(candidato, DateTime.Now.AddSeconds(-20));
                Invocar(v, "Revisar");
                Exigir(intentos == 1 && !File.Exists(Path.Combine(Config.Carpeta, "huellas_enviadas.txt")), "Confirmó captura fallida");
                candidato.GetType().GetField("Reintentar").SetValue(candidato, DateTime.MinValue); aceptar = true;
                Invocar(v, "Revisar");
                Exigir(intentos == 2 && File.ReadAllText(Path.Combine(Config.Carpeta, "huellas_enviadas.txt")).Contains(Vigilante.Huella(b)), "No confirmó reintento");
                Exigir(Directory.GetFiles(Config.Carpeta, "huellas_enviadas.txt.*.tmp").Length == 0, "Dejó temporal de huellas");
                // Un WAV conocido como incompleto nunca se confirma por el mero paso del tiempo.
                string parcial = Path.Combine(Config.Carpeta, "parcial.wav");
                var incompleto = (byte[])b.Clone(); BitConverter.GetBytes((uint)20000).CopyTo(incompleto, 4); File.WriteAllBytes(parcial, incompleto);
                var vp = new Vigilante(); int capturas = 0; vp.AudioListo += (n, d, h) => { capturas++; return true; };
                Invocar(vp, "Anotar", parcial); Invocar(vp, "Revisar");
                var cps = vp.GetType().GetField("candidatos", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(vp);
                object cp = cps.GetType().GetProperty("Item").GetValue(cps, new object[] { parcial });
                cp.GetType().GetField("Visto").SetValue(cp, DateTime.Now.AddMinutes(-2));
                cp.GetType().GetField("UltimoCambio").SetValue(cp, DateTime.Now.AddMinutes(-2));
                Invocar(vp, "Revisar"); Exigir(capturas == 0, "Capturó un WAV truncado tras vencer la espera");
                var completo = new byte[20008]; incompleto.CopyTo(completo, 0); File.WriteAllBytes(parcial, completo);
                cp.GetType().GetField("Reintentar").SetValue(cp, DateTime.MinValue); Invocar(vp, "Revisar");
                cp.GetType().GetField("UltimoCambio").SetValue(cp, DateTime.Now.AddSeconds(-20));
                Invocar(vp, "Revisar"); Exigir(capturas == 1, "No recuperó el WAV completado");
                // Un bloqueo de lectura de más de un minuto no descarta el candidato.
                string ocupado = Path.Combine(Config.Carpeta, "ocupado.wav"); File.WriteAllBytes(ocupado, b);
                var vl = new Vigilante(); int leidos = 0; vl.AudioListo += (n, d, h) => { leidos++; return true; };
                Invocar(vl, "Anotar", ocupado); Invocar(vl, "Revisar");
                var cls = vl.GetType().GetField("candidatos", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(vl);
                object cl = cls.GetType().GetProperty("Item").GetValue(cls, new object[] { ocupado });
                cl.GetType().GetField("Visto").SetValue(cl, DateTime.Now.AddMinutes(-2));
                cl.GetType().GetField("UltimoCambio").SetValue(cl, DateTime.Now.AddMinutes(-2));
                using (var candado = new FileStream(ocupado, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                    Invocar(vl, "Revisar");
                Exigir((bool)cls.GetType().GetMethod("ContainsKey").Invoke(cls, new object[] { ocupado }), "Descartó audio por bloqueo transitorio");
                cl.GetType().GetField("Reintentar").SetValue(cl, DateTime.MinValue);
                Invocar(vl, "Revisar"); Exigir(leidos == 1, "No retomó la lectura al liberar el archivo");
                string desaparecido = Path.Combine(Config.Carpeta, "desaparecido.wav");
                File.WriteAllBytes(desaparecido, b); Invocar(vl, "Anotar", desaparecido); File.Delete(desaparecido);
                Invocar(vl, "Revisar");
                Exigir(!(bool)cls.GetType().GetMethod("ContainsKey").Invoke(cls, new object[] { desaparecido }), "No retiró un original desaparecido");
                // Error real de filesystem antes de publicar: ningún *.audio parcial.
                string bloqueada = Path.Combine(Config.Carpeta, "bloqueada"); Directory.CreateDirectory(bloqueada);
                Config.Carpeta = bloqueada; var colaBloqueada = new ColaEnvio();
                Directory.Move(Path.Combine(bloqueada, "pendientes"), Path.Combine(bloqueada, "apartada"));
                File.WriteAllText(Path.Combine(bloqueada, "pendientes"), "Bloqueo ficticio");
                bool fallo = false; try { colaBloqueada.Agregar("fallo.wav", Datos, Vigilante.Huella(Datos)); } catch (IOException) { fallo = true; }
                Exigir(fallo, "No informó fallo de persistencia");
                // El lector conserva tanto un pendiente v1 ilegible como uno rechazado por la API ficticia.
                Config.Carpeta = Path.Combine(Config.Carpeta, "lector"); Directory.CreateDirectory(Config.Carpeta);
                var lector = new ColaEnvio(); string pendientes = Path.Combine(Config.Carpeta, "pendientes");
                lector.Agregar("rechazado.wav", Datos, Vigilante.Huella(Datos));
                File.WriteAllBytes(Path.Combine(pendientes, "antiguo.audio"), new byte[] { 1, 2, 3 });
                Config.Url = "https://ficticio.invalid"; lector.Iniciar();
                Exigir(System.Threading.SpinWait.SpinUntil(() => lector.Pendientes == 0, 5000), "No aisló ilegibles/rechazados");
                Exigir(Directory.GetFiles(Path.Combine(pendientes, "recuperacion")).Length >= 2, "Perdió archivos rechazados");
                // HTTP 200 sin recibo explícito no autoriza borrar el audio cifrado.
                Config.Carpeta = Path.Combine(Config.Carpeta, "confirmaciones");
                var confirmaciones = new ColaEnvio(); confirmaciones.Agregar("confirmacion-ficticia.wav", Datos, Vigilante.Huella(Datos));
                int ciclos = 0, enviados = 0;
                confirmaciones.PendientesCambio += n => System.Threading.Interlocked.Increment(ref ciclos);
                confirmaciones.Enviado += (n, caso, dup) => System.Threading.Interlocked.Increment(ref enviados);
                var invalidos = new [] {
                    new Dictionary<string,object>(),
                    new Dictionary<string,object> {{"ok",false},{"nombre","caso-ficticio"}},
                    new Dictionary<string,object> {{"ok",true}},
                    new Dictionary<string,object> {{"ok","true"},{"nombre","caso-ficticio"}},
                    new Dictionary<string,object> {{"ok",true},{"nombre","  "}},
                    new Dictionary<string,object> {{"ok",true},{"nombre","caso-ficticio"},{"error","fallo ficticio"}}
                };
                Servidor.Siguiente = new Respuesta { Ok = true, Codigo = 200, Datos = invalidos[0] };
                confirmaciones.Iniciar();
                foreach (var respuesta in invalidos) {
                    Servidor.Siguiente = new Respuesta { Ok = true, Codigo = 200, Datos = respuesta };
                    int anterior = System.Threading.Volatile.Read(ref ciclos);
                    confirmaciones.Despertar();
                    Exigir(System.Threading.SpinWait.SpinUntil(() => System.Threading.Volatile.Read(ref ciclos) > anterior, 5000), "No reintentó confirmación");
                    Exigir(confirmaciones.Pendientes == 1 && enviados == 0, "Borró un audio sin recibo válido");
                }
                Servidor.Siguiente = new Respuesta { Ok = true, Codigo = 200, Datos = new Dictionary<string,object> {{"ok",true},{"nombre","caso-ficticio"}} };
                confirmaciones.Despertar();
                Exigir(System.Threading.SpinWait.SpinUntil(() => System.Threading.Volatile.Read(ref enviados) == 1, 5000), "No confirmó recibo válido");
                Exigir(confirmaciones.Pendientes == 0, "No retiró el audio confirmado");
                Console.WriteLine("OK: cola cifrada, concurrencia, recuperación, cuarentena, confirmación y fallos de escritura."); return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }
    }
}
