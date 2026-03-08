/**
 * Component: Sidebar
 * Purpose: Global navigation sidebar.
 * WHY: Framer Motion provides a premium feeling width transition. Active states hint current location clearly.
 */
import React from 'react';
import { NavLink } from 'react-router';
import { motion } from 'framer-motion';
import { Activity, MessageSquare, PieChart, Settings, Menu, Zap, Bot, ListTree } from 'lucide-react';
import { useStore } from '@/store/useStore';

const Sidebar: React.FC = () => {
  const { isSidebarOpen, toggleSidebar } = useStore();

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: <Activity size={20} /> },
    { name: 'Chat', path: '/chat', icon: <MessageSquare size={20} /> },
    { name: 'Agent', path: '/agent', icon: <Bot size={20} /> },
    { name: 'Traces', path: '/traces', icon: <ListTree size={20} /> },
    { name: 'Analytics', path: '/analytics', icon: <PieChart size={20} /> },
    { name: 'Settings', path: '/settings', icon: <Settings size={20} /> },
  ];

  return (
    <motion.aside
      initial={false}
      animate={{ width: isSidebarOpen ? 240 : 80 }}
      className="h-screen bg-card border-r border-border shadow-2xl flex flex-col pt-6 pb-6 relative z-20 flex-shrink-0"
    >
      <div className="flex items-center justify-between px-6 mb-8">
        <motion.div 
          className="flex items-center gap-3 overflow-hidden"
          animate={{ opacity: 1 }}
        >
          <div className="p-2 bg-primary/20 text-primary rounded-xl glow-effect">
            <Zap size={24} />
          </div>
          {isSidebarOpen && (
            <motion.span 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              className="text-xl font-bold tracking-tight text-foreground"
            >
              LLMWatch
            </motion.span>
          )}
        </motion.div>
      </div>
      
      <nav className="flex-1 px-4 space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `
              flex items-center gap-4 px-3 py-3 rounded-lg transition-all duration-300 group relative overflow-hidden
              ${isActive ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-white/[0.03]'}
            `}
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.div 
                    layoutId="activeTab" 
                    className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r-md glow-effect" 
                  />
                )}
                <div className={`${isActive ? 'text-primary' : 'group-hover:text-foreground'}`}>
                  {item.icon}
                </div>
                {isSidebarOpen && (
                  <motion.span 
                    initial={{ opacity: 0, x: -10 }} 
                    animate={{ opacity: 1, x: 0 }}
                    className="font-medium"
                  >
                    {item.name}
                  </motion.span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Toggle Button */}
      <div className="px-4 mt-auto">
        <button 
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center py-3 bg-white/[0.03] hover:bg-white/[0.08] border border-card-border rounded-xl transition-colors duration-300 cursor-pointer"
        >
          <Menu size={20} className="text-muted-foreground" />
        </button>
      </div>
    </motion.aside>
  );
};

export default Sidebar;
