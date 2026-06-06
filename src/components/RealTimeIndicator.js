import React, { useEffect, useState } from 'react';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';

const RealTimeIndicator = () => {
  const { 
    isConnected, 
    newMessageCount, 
    lastConversationUpdate, 
    reconnect,
    resetNewMessageCount 
  } = useWebSocketContext();
  
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    if (lastConversationUpdate) {
      setLastUpdate(new Date(lastConversationUpdate.timestamp));
    }
  }, [lastConversationUpdate]);

  const handleResetCount = () => {
    resetNewMessageCount();
  };

  return (
    <div className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg">
      {/* Connection Status */}
      <div className="flex items-center gap-1">
        {isConnected ? (
          <>
            <Wifi className="h-4 w-4 text-green-500" />
            <span className="text-xs text-green-600">Connected</span>
          </>
        ) : (
          <>
            <WifiOff className="h-4 w-4 text-red-500" />
            <span className="text-xs text-red-600">Disconnected</span>
            <Button
              size="sm"
              variant="outline"
              onClick={reconnect}
              className="h-6 px-2 text-xs"
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
          </>
        )}
      </div>

      {/* New Messages Badge */}
      {newMessageCount > 0 && (
        <div className="flex items-center gap-1">
          <Badge variant="destructive" className="text-xs">
            {newMessageCount} new
          </Badge>
          <Button
            size="sm"
            variant="ghost"
            onClick={handleResetCount}
            className="h-6 px-2 text-xs"
          >
            Clear
          </Button>
        </div>
      )}

      {/* Last Update Time */}
      {lastUpdate && (
        <div className="text-xs text-gray-500">
          Last: {lastUpdate.toLocaleTimeString()}
        </div>
      )}
    </div>
  );
};

export default RealTimeIndicator;
