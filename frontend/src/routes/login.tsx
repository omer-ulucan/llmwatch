/**
 * Component: Login
 * Purpose: Authentication entrypoint.
 * WHY: High visual impact first impression with animated mesh. Uses Zustand to securely store JWT.
 */
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router';
import { motion } from 'framer-motion';
import { LogIn, Loader2, AlertCircle, ArrowLeft } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useStore } from '@/store/useStore';

const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const navigate = useNavigate();
  const setAuth = useStore(state => state.setAuth);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await apiClient.post('/auth/login', { email, password });
      setAuth(response.data.access_token);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.error || 'Authentication failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background bg-mesh text-foreground font-sans flex items-center justify-center relative overflow-hidden">
      {/* Decorative ambient light */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/20 rounded-full blur-[120px] mix-blend-screen pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-secondary/20 rounded-full blur-[120px] mix-blend-screen pointer-events-none" />
      
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="glass-panel p-10 rounded-3xl w-full max-w-md relative z-10"
      >
        <div className="text-center mb-8">
          <motion.div 
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.3, type: "spring" }}
            className="w-16 h-16 bg-primary/20 text-primary rounded-2xl mx-auto flex items-center justify-center mb-6 glow-effect"
          >
            <LogIn size={32} />
          </motion.div>
          
          <h1 className="text-3xl font-bold tracking-tight mb-2">
            Welcome to <span className="text-gradient">LLMWatch</span>
          </h1>
          <p className="text-muted-foreground">Sign in to monitor your AI infrastructure.</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-5">
          {error && (
            <motion.div 
              initial={{ x: -10, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
               className="flex items-center gap-3 p-3 bg-error-bg text-error rounded-xl text-sm border border-error/20"
            >
              <AlertCircle size={16} />
              {error}
            </motion.div>
          )}

          <div className="space-y-1">
            <label className="text-sm font-medium text-muted-foreground ml-1">Work Email</label>
            <input 
              type="email" 
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-input/50 border border-border rounded-xl px-4 py-3 text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all duration-300"
              placeholder="you@company.com"
            />
          </div>
          
          <div className="space-y-1">
            <label className="text-sm font-medium text-muted-foreground ml-1">Password</label>
            <input 
              type="password" 
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-input/50 border border-border rounded-xl px-4 py-3 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all duration-300"
              placeholder="••••••••"
            />
          </div>

          <button 
            type="submit" 
            disabled={isLoading}
            className="w-full bg-gradient-to-r from-primary to-primary-hover text-white font-medium py-3 rounded-xl shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:shadow-[0_0_30px_rgba(59,130,246,0.5)] transition-all duration-300 flex justify-center items-center mt-4 cursor-pointer"
          >
            {isLoading ? <Loader2 className="animate-spin" size={20} /> : "Sign In"}
          </button>

        </form>

        <div className="mt-6 flex flex-col items-center gap-3">
          <p className="text-sm text-muted-foreground">
            Don&apos;t have an account?{' '}
            <Link to="/signup" className="text-primary hover:text-primary-hover transition-colors font-medium">
              Sign up
            </Link>
          </p>
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft size={14} />
            Back to home
          </Link>
        </div>
      </motion.div>
    </div>
  );
};

export default Login;
