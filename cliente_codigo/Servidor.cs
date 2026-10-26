// Comunicación con el Servidor (por HTTPS, a través del túnel: el rápido de Cloudflare o Microsoft Dev Tunnels).
using System;
using System.Collections.Generic;
using System.Net;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace Transcripcion
{
    class Respuesta
    {
        public int Codigo;                       // 0 = no hubo conexión
        public Dictionary<string, object> Datos;
        public string Error, TextoCrudo;
        public bool Ok { get { return Codigo == 200 && Datos != null; } }
        public string Texto(string clave)
        {
            object v;
            return Datos != null && Datos.TryGetValue(clave, out v) && v != null ? v.ToString() : "";
        }
    }

    static class Servidor
    {
        // Direcciones que se aceptan del canal de avisos (solo de estos dos servicios: si alguien conociera el
        // canal, no podría mandar la app a otro sitio). 1.12: también Microsoft Dev Tunnels; nunca api.trycloudflare.com.
        static readonly Regex DireccionValida = new Regex(
            @"^https://((?!api\.)[a-z0-9]+(-[a-z0-9]+)+\.trycloudflare\.com|[a-z0-9-]+\.[a-z0-9]+\.devtunnels\.ms)$");

        // Microsoft Dev Tunnels muestra una página de aviso ("anti-phishing") la primera vez; este encabezado la saltea.
        public const string SaltarAviso = "X-Tunnel-Skip-AntiPhishing-Page";

        public static bool EsDevTunnel(string url)
        {
            return url != null && url.IndexOf(".devtunnels.ms", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        // Pedido HTTP con HttpWebRequest (viene en el núcleo de .NET Framework, sin dependencias extra).
        static async Task<Respuesta> Enviar(string metodo, string url, string ruta, bool conLlave, byte[] cuerpo,
                                            string tipo, Dictionary<string, string> extra, int segundos)
        {
            try
            {
                var r = (HttpWebRequest)WebRequest.Create(url.TrimEnd(Config.Barra) + ruta);
                r.Method = metodo;
                r.UserAgent = "Transcripcion/" + Programa.VERSION;
                r.AllowAutoRedirect = false;
                r.Timeout = r.ReadWriteTimeout = segundos * 1000;
                r.AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate;
                if (conLlave) r.Headers["Authorization"] = "Bearer " + Config.Llave;
                if (EsDevTunnel(url)) r.Headers[SaltarAviso] = "true";
                if (extra != null) foreach (var kv in extra) r.Headers[kv.Key] = kv.Value;
                if (cuerpo != null)
                {
                    r.ContentType = tipo ?? "application/octet-stream";
                    r.ContentLength = cuerpo.Length;
                    var tarea = Task.Run(async () =>
                    {
                        using (var st = await r.GetRequestStreamAsync().ConfigureAwait(false))
                            await st.WriteAsync(cuerpo, 0, cuerpo.Length).ConfigureAwait(false);
                    });
                    if (await Task.WhenAny(tarea, Task.Delay(segundos * 1000)).ConfigureAwait(false) != tarea) { r.Abort(); throw new TimeoutException("tiempo agotado"); }
                    await tarea.ConfigureAwait(false);
                }
                HttpWebResponse resp;
                var t2 = r.GetResponseAsync();
                if (await Task.WhenAny(t2, Task.Delay(segundos * 1000)).ConfigureAwait(false) != t2) { r.Abort(); throw new TimeoutException("tiempo agotado"); }
                try { resp = (HttpWebResponse)await t2.ConfigureAwait(false); }
                catch (WebException we)
                {
                    resp = we.Response as HttpWebResponse;
                    if (resp == null) throw;
                }
                using (resp)
                {
                    string txt;
                    using (var sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8)) txt = await sr.ReadToEndAsync().ConfigureAwait(false);
                    Dictionary<string, object> d = null;
                    try { if (txt.TrimStart().StartsWith("{")) d = Config.Json.Deserialize<Dictionary<string, object>>(txt); } catch { }
                    var res = new Respuesta { Codigo = (int)resp.StatusCode, Datos = d, TextoCrudo = txt };
                    if (d != null && d.ContainsKey("error")) res.Error = d["error"] + "";
                    else if (res.Codigo != 200) res.Error = "El Servidor respondió " + res.Codigo;
                    return res;
                }
            }
            catch (Exception ex)
            {
                return new Respuesta { Codigo = 0, Error = "Sin conexión (" + (ex.InnerException ?? ex).Message + ")" };
            }
        }

        static byte[] ComoJson(object o) { return Encoding.UTF8.GetBytes(Config.Json.Serialize(o)); }

        public static Task<Respuesta> Estado(string url)
        {
            return Enviar("GET", url, "/api/cliente/estado", true, null, null, null, 20);
        }

        public static Task<Respuesta> Vincular(string url, string pc, string contrasena)
        {
            return Enviar("POST", url, "/api/cliente/vincular", false,
                ComoJson(new Dictionary<string, object> { { "pc", pc }, { "contrasena", contrasena } }), "application/json", null, 30);
        }

        public static Task<Respuesta> Sesion(string url)
        {
            return Enviar("POST", url, "/api/cliente/sesion", true, new byte[0], "application/json", null, 20);
        }

        // ---- actualización de la app
        public static Task<Respuesta> Manifiesto(string url)
        {
            return Enviar("GET", url, "/api/cliente/actualizacion", true, null, null, null, 30);
        }

        public static Task<Respuesta> Avisar(string url, string texto, string tipo)
        {
            return Enviar("POST", url, "/api/cliente/aviso", true,
                ComoJson(new Dictionary<string, object> { { "texto", texto }, { "tipo", tipo } }), "application/json", null, 20);
        }

        // Baja un archivo de la app a 'destino'. Devuelve null si salió bien, o el error.
        public static string Bajar(string url, string rel, string destino)
        {
            string tmp = destino + ".parcial";
            try
            {
                var r = (HttpWebRequest)WebRequest.Create(url.TrimEnd(Config.Barra) + "/api/cliente/archivo?ruta=" + Uri.EscapeDataString(rel));
                r.Method = "GET";
                r.UserAgent = "Transcripcion/" + Programa.VERSION;
                r.AllowAutoRedirect = false;
                r.Timeout = r.ReadWriteTimeout = 120000;
                r.Headers["Authorization"] = "Bearer " + Config.Llave;
                using (var resp = (HttpWebResponse)r.GetResponse())
                {
                    if (resp.StatusCode != HttpStatusCode.OK) return "el Servidor respondió " + (int)resp.StatusCode;
                    using (var st = resp.GetResponseStream())
                    using (var f = new FileStream(tmp, FileMode.Create, FileAccess.Write))
                        st.CopyTo(f);
                }
                if (File.Exists(destino)) File.Delete(destino);
                File.Move(tmp, destino);
                return null;
            }
            catch (WebException we)
            {
                var resp = we.Response as HttpWebResponse;
                try { if (File.Exists(tmp)) File.Delete(tmp); } catch { }
                return resp != null ? "el Servidor respondió " + (int)resp.StatusCode : we.Message;
            }
            catch (Exception ex)
            {
                try { if (File.Exists(tmp)) File.Delete(tmp); } catch { }
                return ex.Message;
            }
        }

        public static Task<Respuesta> SubirAudio(string url, string nombreOriginal, byte[] datos, string huella)
        {
            var extra = new Dictionary<string, string> { { "X-Archivo", Uri.EscapeDataString(nombreOriginal) }, { "X-Huella", huella } };
            return Enviar("POST", url, "/api/cliente/audio", true, datos, "audio/wav", extra, 180);
        }

        // La dirección del túnel cambia cuando el Servidor se reinicia. El Servidor la publica en un canal
        // de avisos con nombre secreto (conexion.json); acá se lee el último aviso.
        public static async Task<string> BuscarDireccion()
        {
            if (string.IsNullOrEmpty(Config.Tema)) return null;
            var r = await Enviar("GET", Config.Aviso, "/" + Config.Tema + "/json?poll=1&since=24h", false, null, null, null, 20).ConfigureAwait(false);
            if (r.Codigo != 200 || r.TextoCrudo == null)
            {
                Registro.Escribir("No se pudo leer el canal de avisos: " + r.Error);
                return null;
            }
            string ultima = null;
            foreach (string linea in r.TextoCrudo.Split('\n'))
            {
                if (linea.Trim() == "") continue;
                try
                {
                    var d = Config.Json.Deserialize<Dictionary<string, object>>(linea);
                    object ev, msg;
                    if (d.TryGetValue("event", out ev) && ev + "" == "message" && d.TryGetValue("message", out msg))
                    {
                        string m = (msg + "").Trim().TrimEnd(Config.Barra);
                        if (DireccionValida.IsMatch(m)) ultima = m;
                    }
                }
                catch { }
            }
            return ultima;
        }

        public static string Normalizar(string url)
        {
            url = (url ?? "").Trim().TrimEnd(Config.Barra);
            if (url != "" && !url.StartsWith("http", StringComparison.OrdinalIgnoreCase)) url = "https://" + url;
            Uri u;
            if (url != "" && Uri.TryCreate(url, UriKind.Absolute, out u) && (u.Scheme == "https" || u.Scheme == "http") && u.Host != "")
                url = u.GetLeftPart(UriPartial.Authority);
            return url;
        }
    }
}
