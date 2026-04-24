import { useState, useEffect, useRef } from 'react';
import { Database, ArrowRight, BarChart3, Code, Table } from 'lucide-react';

interface FallingColumn {
  id: number;
  x: number;
  speed: number;
  characters: string[];
  yPositions: number[];
}

export function LandingPage({ onEnter }: { onEnter: () => void }) {
  const [isDarkMode] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Data characters to use - more visible data symbols
    const dataChars = '0123456789ABCDEF%$#@+-*/=<>[]{}().,:|&^~';
    const columnWidth = 24;
    const numColumns = Math.floor(canvas.width / columnWidth);

    const columns: FallingColumn[] = [];
    for (let i = 0; i < numColumns; i++) {
      const numChars = Math.floor(Math.random() * 25) + 15;
      columns.push({
        id: i,
        x: i * columnWidth,
        speed: Math.random() * 2.5 + 0.8,
        characters: Array(numChars).fill(0).map(() =>
          dataChars[Math.floor(Math.random() * dataChars.length)]
        ),
        yPositions: Array(numChars).fill(0).map((_, idx) => idx * -28)
      });
    }

    let animationId: number;

    const animate = () => {
      // Semi-transparent background for trail effect
      if (isDarkMode) {
        ctx.fillStyle = 'rgba(17, 24, 39, 0.08)';
      } else {
        ctx.fillStyle = 'rgba(255, 250, 240, 0.08)';
      }
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      columns.forEach(column => {
        column.characters.forEach((char, idx) => {
          const y = column.yPositions[idx];

          // Color gradient - lighter at the head with better visibility
          const opacity = idx === 0 ? 1 : Math.max(0.2, 1 - idx * 0.04);

          if (isDarkMode) {
            ctx.fillStyle = idx === 0
              ? `rgba(37, 99, 235, ${opacity})`
              : `rgba(59, 130, 246, ${opacity * 0.7})`;
          } else {
            ctx.fillStyle = idx === 0
              ? `rgba(37, 99, 235, ${opacity * 0.6})`
              : `rgba(59, 130, 246, ${opacity * 0.35})`;
          }

          ctx.font = 'bold 16px monospace';
          ctx.fillText(char, column.x, y);
        });

        // Move column down
        column.yPositions = column.yPositions.map(y => y + column.speed);

        // Reset if all characters are off screen
        if (column.yPositions[column.yPositions.length - 1] > canvas.height + 100) {
          column.yPositions = column.yPositions.map((_, idx) => idx * -25);
          column.characters = column.characters.map(() =>
            dataChars[Math.floor(Math.random() * dataChars.length)]
          );
          column.speed = Math.random() * 2 + 1;
        }
      });

      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationId);
    };
  }, [isDarkMode]);

  const bgColor = isDarkMode ? 'bg-[#111827]' : 'bg-[#FFFAF0]';
  const textPrimary = isDarkMode ? 'text-white' : 'text-gray-900';
  const textSecondary = isDarkMode ? 'text-gray-400' : 'text-gray-600';

  return (
    <div className={`relative min-h-screen ${bgColor} overflow-hidden`}>
      {/* Cascading data background */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none"
        style={{ opacity: isDarkMode ? 0.4 : 0.25 }}
      />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-4">
        <div className="text-center max-w-4xl mx-auto">
          {/* Logo/Icon */}
          <div className="mb-8 inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-[#2563EB] to-[#1d4ed8] shadow-lg">
            <Database className="w-10 h-10 text-white" strokeWidth={2} />
          </div>

          {/* Main Heading */}
          <h1 className={`text-5xl md:text-6xl font-bold mb-6 ${textPrimary}`}>
            DataAnalyst AI
          </h1>

          <p className={`text-xl md:text-2xl mb-12 ${textSecondary} max-w-2xl mx-auto`}>
            Transform your data into insights with AI-powered analysis
          </p>

          {/* Feature Pills */}
          <div className="flex flex-wrap gap-3 justify-center mb-12">
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} shadow-md`}>
              <BarChart3 className="w-4 h-4 text-[#2563EB]" strokeWidth={2} />
              <span className={`text-sm ${textPrimary}`}>Advanced Analytics</span>
            </div>
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} shadow-md`}>
              <Code className="w-4 h-4 text-[#2563EB]" strokeWidth={2} />
              <span className={`text-sm ${textPrimary}`}>Auto Code Generation</span>
            </div>
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full ${isDarkMode ? 'bg-gray-800' : 'bg-white'} shadow-md`}>
              <Table className="w-4 h-4 text-[#2563EB]" strokeWidth={2} />
              <span className={`text-sm ${textPrimary}`}>Multi-format Support</span>
            </div>
          </div>

          {/* CTA Button */}
          <button
            onClick={onEnter}
            className="group inline-flex items-center gap-2 px-8 py-4 bg-[#2563EB] hover:bg-[#1d4ed8] text-white text-lg font-semibold rounded-lg shadow-lg transition-all transform hover:scale-105"
          >
            Get Started
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" strokeWidth={2} />
          </button>

          {/* Stats */}
          <div className="mt-16 grid grid-cols-3 gap-8 max-w-2xl mx-auto">
            <div>
              <div className={`text-3xl font-bold ${textPrimary} mb-1`}>10K+</div>
              <div className={`text-sm ${textSecondary}`}>Datasets Analyzed</div>
            </div>
            <div>
              <div className={`text-3xl font-bold ${textPrimary} mb-1`}>50K+</div>
              <div className={`text-sm ${textSecondary}`}>Insights Generated</div>
            </div>
            <div>
              <div className={`text-3xl font-bold ${textPrimary} mb-1`}>99.9%</div>
              <div className={`text-sm ${textSecondary}`}>Accuracy Rate</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
