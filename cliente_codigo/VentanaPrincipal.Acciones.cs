// Acciones: cargar un audio, dirección a mano, conectar a otro Servidor, desvincular, abrir carpetas y pedir textos.
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
            string url = Pedir("Dirección del Servidor", "Pegá la dirección del Servidor (termina en devtunnels.ms o en trycloudflare.com):", Config.Url);
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
                Text = Config.NombreVisible + " — " + Config.Pc;
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
