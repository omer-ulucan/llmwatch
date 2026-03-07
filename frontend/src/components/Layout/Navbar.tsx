/**
 * Component: Navbar
 * Purpose: Top header with breadcrumbs and user controls.
 * WHY: Always visible contextual anchor points keep the user oriented.
 */
import React from 'react';
import { useLocation, useNavigate } from 'react-router';
import { motion } from 'framer-motion';
import { LogOut } from 'lucide-react';
import { useStore } from '@/store/useStore';

const Navbar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useStore(state => state.logout);
  const pathName = location.pathname.split('/').pop();
  const title = pathName ? pathName.charAt(0).toUpperCase() + pathName.slice(1) : 'Dashboard';

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-20 w-full flex items-center justify-between px-8 bg-background/50 backdrop-blur-xl border-b border-border z-10 sticky top-0">
      <div className="flex items-center gap-4">
        <motion.h2 
          key={title}
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-2xl font-semibold tracking-tight"
        >
          {title}
        </motion.h2>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3 px-4 py-2 glass-card rounded-full cursor-pointer hover:bg-white/[0.05]">
          <div className="w-8 h-8 rounded-full bg-secondary/20 flex items-center justify-center text-secondary font-medium">
            A
          </div>
          <span className="text-sm font-medium pr-2 text-muted-foreground">Admin</span>
        </div>
        
        <button 
          onClick={handleLogout}
          className="p-2 cursor-pointer text-muted-foreground hover:text-error transition-colors bg-white/[0.02] border border-card-border rounded-xl hover:bg-error/10 hover:border-error/30"
          title="Logout"
        >
          <LogOut size={20} />
        </button>
      </div>
    </header>
  );
};

export default Navbar;
