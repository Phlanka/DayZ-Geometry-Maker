class ActionClose_CLASSNAME: ActionInteractBase
{
	void ActionClose_CLASSNAME()
	{
		m_CommandUID = DayZPlayerConstants.CMD_ACTIONMOD_INTERACTONCE;
		m_StanceMask = DayZPlayerConstants.STANCEMASK_ERECT | DayZPlayerConstants.STANCEMASK_CROUCH;
		m_Text = "#close";
	}

	override bool ActionCondition( PlayerBase player, ActionTarget target, ItemBase item )
	{
		Object target_object = target.GetObject();
		if ( target_object.IsItemBase() )
		{
			CLASSNAME ntarget = CLASSNAME.Cast( target_object );
			if( ntarget )
			{
				if ( !ntarget.IsLocked() && ntarget.IsOpen() )
				{
					return true;
				}
			}
		}
		return false;
	}

	override void OnExecuteServer( ActionData action_data )
	{
		Object target_object = action_data.m_Target.GetObject();
		CLASSNAME ntarget = CLASSNAME.Cast( target_object );
		if( ntarget )
		{
			ntarget.Close();
		}
	}

	override void OnEndServer( ActionData action_data )
	{
		Object target_object = action_data.m_Target.GetObject();
		CLASSNAME ntarget = CLASSNAME.Cast( target_object );
		if( ntarget )
		{
			ntarget.SoundSynchRemoteReset();
		}
	}
}
