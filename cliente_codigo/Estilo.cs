// Colores, letras e íconos (los mismos de la interfaz web).
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace Transcripcion
{
    static class Estilo
    {
        public static readonly Color Fondo = Color.FromArgb(0xf3, 0xf2, 0xef);
        public static readonly Color Panel = Color.FromArgb(0xfb, 0xfb, 0xfa);
        public static readonly Color Borde = Color.FromArgb(0xcf, 0xcd, 0xc6);
        public static readonly Color Linea = Color.FromArgb(0xe0, 0xdf, 0xda);
        public static readonly Color Texto = Color.FromArgb(0x1d, 0x1d, 0x1b);
        public static readonly Color TextoSuave = Color.FromArgb(0x5c, 0x5b, 0x55);
        public static readonly Color Azul = Color.FromArgb(0x1f, 0x5f, 0xbf);
        public static readonly Color Verde = Color.FromArgb(0x2e, 0x7d, 0x4f);
        public static readonly Color Ambar = Color.FromArgb(0x8a, 0x65, 0x00);
        public static readonly Color Naranja = Color.FromArgb(0xc7, 0x77, 0x00);
        public static readonly Color Rojo = Color.FromArgb(0xb3, 0x26, 0x1e);
        public static readonly Color FondoAmbar = Color.FromArgb(0xff, 0xf6, 0xdc);
        public static readonly Color FondoRojo = Color.FromArgb(0xfd, 0xec, 0xea);
        public static readonly Color Oscuro = Color.FromArgb(0x1d, 0x1d, 0x1b);

        public static readonly Font Fuente = new Font("Segoe UI", 9.75f);
        public static readonly Font Negrita = new Font("Segoe UI", 9.75f, FontStyle.Bold);
        public static readonly Font Chica = new Font("Segoe UI", 8.75f);
        public static readonly Font Titulo = new Font("Segoe UI", 15f, FontStyle.Bold);
        public static readonly Font Mono = new Font("Consolas", 9f);

        [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr h);

        // Ícono: cinco barras de una onda de sonido, del color del estado.
        public static Icon Icono(Color c)
        {
            using (var bmp = new Bitmap(32, 32))
            {
                using (var g = Graphics.FromImage(bmp))
                using (var p = new Pen(c, 3.4f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.Clear(Color.Transparent);
                    int[] alto = { 5, 13, 22, 11, 5 };
                    for (int i = 0; i < 5; i++)
                    {
                        float x = 4 + i * 6f, h = alto[i];
                        g.DrawLine(p, x, 16 - h / 2, x, 16 + h / 2);
                    }
                }
                IntPtr hi = bmp.GetHicon();
                var ico = (Icon)Icon.FromHandle(hi).Clone();
                try { DestroyIcon(hi); } catch { }
                return ico;
            }
        }
    }
}
