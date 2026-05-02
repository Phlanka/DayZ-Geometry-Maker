modded class ActionConstructor
{
    override void RegisterActions (TTypenameArray actions)
    {
        super.RegisterActions (actions);
        actions.Insert (ActionClose_CLASSNAME);
        actions.Insert (ActionOpen_CLASSNAME);
    };
};
