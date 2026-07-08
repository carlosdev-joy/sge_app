const TypingIndicator = () => {
  return (
    <div className="flex items-center gap-1">
      <div className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:0ms]"></div>
      <div className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:150ms]"></div>
      <div className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:300ms]"></div>
    </div>
  );
};

export default TypingIndicator;
